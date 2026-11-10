"""文本向量化（bge-small-zh-v1.5，ADR-015：CPU 版 torch）。

模型缓存在 MODEL_CACHE_DIR；首次使用时从 HF_ENDPOINT（国内用 hf-mirror.com）下载，
建议在 make init 阶段预先下载（python -m scripts.download_models）。
不可用时抛出异常，调用方（构建批次、锚点召回）降级为 graph_only。
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_env


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    env = get_env()
    return SentenceTransformer(env.embedding_model, device="cpu", cache_folder=env.model_cache_dir)


def embed(texts: list[str]):
    """返回 float32、L2 归一化的 numpy 矩阵（内积即余弦相似度）。"""
    import numpy as np

    if get_env().embedding_provider == "api":
        from app.llm.embedding_api import embed as api_embed

        return api_embed(texts)
    vecs = _model().encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return np.asarray(vecs, dtype="float32")


def identity() -> dict:
    """No secrets in index metadata; include endpoint to distinguish model aliases."""
    env = get_env()
    return {
        "provider": env.embedding_provider,
        "model": env.embedding_model,
        "endpoint": env.embedding_base_url.rstrip("/") if env.embedding_provider == "api" else "",
        "configured_dimensions": env.embedding_dimensions,
    }
