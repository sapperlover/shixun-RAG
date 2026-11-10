"""Persistent conservative embedding budget. Does not store source text or credentials."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from app.core.config import get_env


class TokenBudgetExceeded(ValueError):
    pass


@contextmanager
def _state():
    env = get_env()
    target = Path(env.embedding_usage_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_suffix(".lock")
    deadline = time.monotonic() + 10
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise TokenBudgetExceeded(
                    "Embedding budget ledger is locked; no request sent"
                ) from None
            time.sleep(0.05)
    try:
        state = (
            json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"events": []}
        )
        state["untracked_historical_reserve"] = max(
            state.get("untracked_historical_reserve", 0), env.embedding_untracked_reserve
        )
        state["limit"] = env.embedding_token_limit
        yield state
        state["conservative_total"] = state["untracked_historical_reserve"] + sum(
            e["charged_tokens"] for e in state["events"]
        )
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(target)
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def reserve(texts: list[str]) -> str | None:
    env = get_env()
    if env.embedding_token_limit is None:
        return None
    # Byte-level upper reservation + per-input framing allowance; unknown failures
    # retain the full reservation rather than assuming the server did no work.
    upper = sum(len(t.encode("utf-8")) + 16 for t in texts)
    with _state() as state:
        total = state["untracked_historical_reserve"] + sum(
            e["charged_tokens"] for e in state["events"]
        )
        if total + upper > env.embedding_token_limit:
            raise TokenBudgetExceeded(
                f"Embedding token budget would be exceeded ({total}+{upper}); no request sent"
            )
        event_id = uuid.uuid4().hex
        state["events"].append(
            {
                "id": event_id,
                "model": env.embedding_model,
                "input_count": len(texts),
                "reserved_upper": upper,
                "charged_tokens": upper,
                "reported_tokens": None,
                "state": "pending_or_unknown",
            }
        )
    return event_id


def settle(
    event_id: str | None, payload: dict | None, *, rejected: bool = False, not_sent: bool = False
):
    if event_id is None:
        return
    usage = (payload or {}).get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    count = next(
        (
            usage[k]
            for k in ("total_tokens", "input_tokens", "prompt_tokens")
            if type(usage.get(k)) is int and usage[k] >= 0
        ),
        None,
    )
    with _state() as state:
        event = next(e for e in state["events"] if e["id"] == event_id)
        event["reported_tokens"] = count
        event["charged_tokens"] = (
            count if count is not None else 0 if rejected or not_sent else event["reserved_upper"]
        )
        event["state"] = (
            "provider_reported"
            if count is not None
            else "rejected"
            if rejected
            else "unreported_upper_bound"
        )
        if not_sent:
            event["state"] = "connection_failed_before_request"
