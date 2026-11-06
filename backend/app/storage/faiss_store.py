"""FAISS 向量索引（V1.2 §2）：每个 batch 一个目录 {FAISS_DIR}/{batch_id}/，随批次一起构建和发布。

TODO(BE, D3)：引入 faiss-cpu 与 bge-small-zh-v1.5 后实现 build / search。
不可用时调用方必须显式降级为 retrieval_mode=graph_only，并标记 degraded_mode。
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_env


def index_dir(batch_id: str) -> Path:
    return Path(get_env().faiss_dir) / batch_id


def status(batch_id: str | None) -> str:
    if batch_id is None:
        return "no active batch"
    return "ready" if (index_dir(batch_id) / "index.faiss").exists() else "not built"


def search(batch_id: str, text: str, k: int) -> list[tuple[str, float]]:
    """返回 [(entity_id, score)]。"""
    raise NotImplementedError("FAISS 检索尚未实现（D3）")
