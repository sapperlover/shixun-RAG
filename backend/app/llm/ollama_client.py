"""Ollama 客户端。模型名来自 .env 的 LLM_MODEL；参数来自 settings.yaml 的 generation。"""

from __future__ import annotations

import httpx

from app.core.config import get_env, get_settings
from app.core.errors import ErrorCode, ServiceUnavailable


def ping() -> str:
    """检查服务可达且模型已拉取。"""
    env = get_env()
    try:
        r = httpx.get(f"{env.ollama_base_url}/api/tags", timeout=3)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceUnavailable(ErrorCode.LLM_UNAVAILABLE, str(exc)) from exc
    names = {m.get("name") for m in r.json().get("models", [])}
    if env.llm_model not in names:
        raise ServiceUnavailable(ErrorCode.LLM_UNAVAILABLE, f"模型 {env.llm_model} 未拉取")
    return env.llm_model


def chat_json(system: str, user: str) -> str:
    """以 JSON 模式调用模型，返回原始文本（由调用方解析和校验）。"""
    env, gen = get_env(), get_settings().generation
    try:
        r = httpx.post(
            f"{env.ollama_base_url}/api/chat",
            json={
                "model": env.llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": gen.temperature, "num_predict": gen.max_tokens},
            },
            timeout=gen.timeout_s,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceUnavailable(ErrorCode.LLM_UNAVAILABLE, str(exc)) from exc
    return r.json()["message"]["content"]
