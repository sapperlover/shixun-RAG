"""API 文本向量化；索引绑定模型、端点和维度，避免混用不同向量空间。"""

from __future__ import annotations

from app.core.config import get_env


def embed(texts: list[str]):
    """返回 float32、L2 归一化的 numpy 矩阵（内积即余弦相似度）。"""
    from app.llm.embedding_api import embed as api_embed

    return api_embed(texts)


def identity() -> dict:
    """No secrets in index metadata; include endpoint to distinguish model aliases."""
    env = get_env()
    return {
        "provider": env.embedding_provider,
        "model": env.embedding_model,
        "endpoint": env.embedding_base_url.rstrip("/") if env.embedding_provider == "api" else "",
        "configured_dimensions": env.embedding_dimensions,
    }
