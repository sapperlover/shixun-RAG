import json

import httpx
import pytest

from app.core.config import EnvSettings
from app.core.errors import ServiceUnavailable
from app.llm import chat_api


@pytest.fixture
def api(monkeypatch):
    settings = EnvSettings(
        llm_base_url="https://model.test/v1", llm_model="test-model", llm_api_key="private-test-key"
    )
    monkeypatch.setattr(chat_api, "get_env", lambda: settings)
    original = httpx.Client

    def install(handler):
        monkeypatch.setattr(
            chat_api.httpx,
            "Client",
            lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
        )

    return settings, install


def test_chat_api_sends_server_key_and_json_request(api):
    settings, install = api

    def handler(request):
        assert str(request.url) == "https://model.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer private-test-key"
        payload = json.loads(request.content)
        assert payload["model"] == settings.llm_model
        assert payload["response_format"] == {"type": "json_object"}
        assert [m["role"] for m in payload["messages"]] == ["system", "user"]
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"claims": []}'}}]})

    install(handler)
    assert chat_api.chat_json("rules", "question") == '{"claims": []}'
    settings.llm_base_url += "/chat/completions"
    assert chat_api.configuration()[0] == "https://model.test/v1/chat/completions"


@pytest.mark.parametrize("failure", [401, 429, 500, "timeout", "malformed", "empty"])
def test_chat_errors_are_sanitized(api, failure):
    _, install = api

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private-test-key provider error", request=request)
        if isinstance(failure, int):
            return httpx.Response(failure, text="private-test-key provider error")
        if failure == "empty":
            return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
        return httpx.Response(200, json={"unexpected": "private-test-key"})

    install(handler)
    with pytest.raises(ServiceUnavailable) as exc:
        chat_api.chat_json("rules", "question")
    assert "private-test-key" not in str(exc.value)
    assert "provider error" not in str(exc.value)


def test_health_probe_does_not_charge_and_missing_configuration_fails(api):
    settings, install = api
    install(lambda _: pytest.fail("Health probes must not call the provider"))
    assert "configured" in chat_api.ping()
    settings.llm_api_key = ""
    with pytest.raises(ServiceUnavailable):
        chat_api.ping()


@pytest.mark.parametrize("thinking", ["", "disabled", "enabled"])
def test_optional_thinking_parameter_is_only_sent_when_configured(api, thinking):
    settings, install = api
    settings.llm_thinking = thinking

    def handler(request):
        payload = json.loads(request.content)
        if thinking:
            assert payload["thinking"] == {"type": thinking}
        else:
            assert "thinking" not in payload
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"claims": []}'}}]})

    install(handler)
    assert chat_api.chat_json("Return JSON", "question") == '{"claims": []}'
