"""Configurable OpenAI-compatible chat API; no local model runtime."""

from __future__ import annotations

import httpx

from app.core.config import get_env, get_settings
from app.core.errors import ErrorCode, ServiceUnavailable


def configuration() -> tuple[str, dict[str, str]]:
    env = get_env()
    if not (env.llm_base_url.strip() and env.llm_api_key.strip() and env.llm_model.strip()):
        raise ServiceUnavailable(
            ErrorCode.LLM_UNAVAILABLE, "请配置 LLM_BASE_URL、LLM_MODEL 和 LLM_API_KEY"
        )
    base = env.llm_base_url.rstrip("/")
    url = base if base.endswith("/chat/completions") else base + "/chat/completions"
    return url, {"Authorization": f"Bearer {env.llm_api_key}"}


def ping() -> str:
    """Check configuration without charging for a generation on every health probe."""
    configuration()
    return f"{get_env().llm_model} (API configured; actual connectivity checked by questions)"


def chat_json(system: str, user: str) -> str:
    env, generation = get_env(), get_settings().generation
    url, headers = configuration()
    payload = {
        "model": env.llm_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "temperature": generation.temperature,
        "max_tokens": generation.max_tokens,
    }
    if env.llm_json_mode:
        payload["response_format"] = {"type": "json_object"}
    if env.llm_thinking:
        payload["thinking"] = {"type": env.llm_thinking}
    try:
        with httpx.Client(timeout=generation.timeout_s, trust_env=env.llm_trust_env) as client:
            response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty model response")
        return content
    except httpx.HTTPStatusError as exc:
        raise ServiceUnavailable(
            ErrorCode.LLM_UNAVAILABLE, f"生成 API 返回 HTTP {exc.response.status_code}"
        ) from None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        raise ServiceUnavailable(
            ErrorCode.LLM_UNAVAILABLE, "生成 API 超时、不可达或响应格式不正确"
        ) from None
