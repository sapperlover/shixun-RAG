"""OpenAI-compatible embedding transport. Does not choose a model or endpoint."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

import httpx
import numpy as np

from app.core.config import get_env
from app.llm import token_budget


class EmbeddingError(ValueError):
    """Configuration, transport or embedding response is unusable."""


def embed(texts: list[str]) -> np.ndarray:
    env = get_env()
    if not (env.embedding_base_url and env.embedding_model and env.embedding_api_key):
        raise EmbeddingError("Embedding API requires base URL, model and API key")
    if env.embedding_dimensions is None:
        raise EmbeddingError("EMBEDDING_DIMENSIONS must be supplied for API embeddings")
    if not texts:
        return np.empty((0, env.embedding_dimensions), dtype="float32")
    batches = []
    with httpx.Client(timeout=env.embedding_timeout_s, trust_env=env.embedding_trust_env) as client:
        for start in range(0, len(texts), env.embedding_batch_size):
            part = texts[start : start + env.embedding_batch_size]
            payload = {"model": env.embedding_model, "input": part}
            cache = None
            if env.embedding_cache_enabled:
                key = hashlib.sha256(
                    json.dumps(
                        {
                            **payload,
                            "endpoint": env.embedding_base_url,
                            "dimensions": env.embedding_dimensions,
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                cache = Path(env.embedding_request_cache) / (key + ".npy")
                if cache.exists():
                    matrix = np.load(cache, allow_pickle=False)
                    if (
                        matrix.shape != (len(part), env.embedding_dimensions)
                        or not np.isfinite(matrix).all()
                        or (np.abs(np.linalg.norm(matrix, axis=1) - 1) > 0.01).any()
                    ):
                        raise EmbeddingError("Cached embedding response is invalid")
                    batches.append(matrix)
                    continue
            # Dimension is a validation contract, not a request parameter: some providers
            # support only the model's native dimension and reject `dimensions`.
            for attempt in range(env.embedding_max_retries + 1):
                reservation = token_budget.reserve(part)
                try:
                    response = client.post(
                        env.embedding_base_url.rstrip("/") + "/embeddings",
                        headers={"Authorization": f"Bearer {env.embedding_api_key}"},
                        json=payload,
                    )
                except httpx.TransportError as exc:
                    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                        token_budget.settle(reservation, None, not_sent=True)
                    if attempt == env.embedding_max_retries:
                        raise EmbeddingError("Embedding transport unavailable") from None
                    time.sleep(min(2**attempt, 4))
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    token_budget.settle(reservation, None, rejected=response.status_code == 429)
                    if attempt == env.embedding_max_retries:
                        raise EmbeddingError(f"Embedding HTTP {response.status_code}")
                    try:
                        delay = float(response.headers.get("Retry-After", 2**attempt))
                    except ValueError:
                        delay = 2**attempt
                    time.sleep(max(0, min(delay, 5)))
                    continue
                if not response.is_success:
                    # Never include response body, request headers or credentials in logs.
                    token_budget.settle(
                        reservation, None, rejected=400 <= response.status_code < 500
                    )
                    raise EmbeddingError(f"Embedding HTTP {response.status_code}")
                try:
                    parsed = response.json()
                    if not isinstance(parsed, dict):
                        raise ValueError("response must be an object")
                    token_budget.settle(reservation, parsed)
                    data = parsed["data"]
                    if len(data) != len(part):
                        raise ValueError("count")
                    if any(type(row["index"]) is not int for row in data):
                        raise ValueError("index")
                    if sorted(row["index"] for row in data) != list(range(len(part))):
                        raise ValueError("index")
                    if any(type(v) not in (int, float) for row in data for v in row["embedding"]):
                        raise ValueError("numeric values required")
                    matrix = np.asarray(
                        [r["embedding"] for r in sorted(data, key=lambda r: r["index"])],
                        dtype="float32",
                    )
                    if matrix.shape != (len(part), env.embedding_dimensions):
                        raise ValueError("shape")
                    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
                    if not np.isfinite(matrix).all() or not np.isfinite(norms).all():
                        raise ValueError("finite")
                    if (norms <= 0).any():
                        raise ValueError("zero")
                    normalized = np.ascontiguousarray(matrix / norms, dtype="float32")
                    batches.append(normalized)
                    if cache:
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        temporary = cache.with_suffix("." + uuid.uuid4().hex + ".npy")
                        np.save(temporary, normalized, allow_pickle=False)
                        temporary.replace(cache)
                except (ValueError, KeyError, TypeError, OverflowError):
                    raise EmbeddingError(
                        "Invalid embedding response (count/index/dimension/value)"
                    ) from None
                break
    return np.concatenate(batches, axis=0)
