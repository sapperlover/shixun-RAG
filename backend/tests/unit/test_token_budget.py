import json

import pytest

from app.core.config import EnvSettings
from app.llm import token_budget


def test_budget_reserves_before_request_and_uses_provider_usage(tmp_path, monkeypatch):
    target = tmp_path / "usage.json"
    env = EnvSettings(
        embedding_token_limit=100, embedding_untracked_reserve=20, embedding_usage_path=str(target)
    )
    monkeypatch.setattr(token_budget, "get_env", lambda: env)
    event = token_budget.reserve(["test"])
    token_budget.settle(event, {"usage": {"input_tokens": 3}})
    state = json.loads(target.read_text())
    assert state["conservative_total"] == 23
    assert state["events"][0]["reported_tokens"] == 3
    with pytest.raises(token_budget.TokenBudgetExceeded):
        token_budget.reserve(["a" * 100])
    assert len(json.loads(target.read_text())["events"]) == 1


def test_unknown_transport_keeps_upper_reservation(tmp_path, monkeypatch):
    target = tmp_path / "usage.json"
    env = EnvSettings(embedding_token_limit=100, embedding_usage_path=str(target))
    monkeypatch.setattr(token_budget, "get_env", lambda: env)
    token_budget.reserve(["test"])
    state = json.loads(target.read_text())
    assert state["conservative_total"] == 20
    assert state["events"][0]["state"] == "pending_or_unknown"


def test_connection_failure_before_sending_releases_reservation(tmp_path, monkeypatch):
    target = tmp_path / "usage.json"
    env = EnvSettings(embedding_token_limit=100, embedding_usage_path=str(target))
    monkeypatch.setattr(token_budget, "get_env", lambda: env)
    event = token_budget.reserve(["test"])
    token_budget.settle(event, None, not_sent=True)
    state = json.loads(target.read_text())
    assert state["conservative_total"] == 0
    assert state["events"][0]["state"] == "connection_failed_before_request"
