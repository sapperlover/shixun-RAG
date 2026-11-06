"""FAISS 向量索引（V1.2 §2）：每个 batch 一个目录 {FAISS_DIR}/{batch_id}/，随批次构建，与图谱同批发布。

索引内容：本批次实体的名称与别名（用于锚点的向量召回）。
不可用（未安装依赖、模型未下载、索引缺失）时抛出异常，调用方显式降级为 graph_only。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core.config import get_env


def index_dir(batch_id: str) -> Path:
    return Path(get_env().faiss_dir) / batch_id


def status(batch_id: str | None) -> str:
    if batch_id is None:
        return "no active batch"
    return "ready" if (index_dir(batch_id) / "index.faiss").exists() else "not built"


def build(batch_id: str, items: list[tuple[str, str, str]]) -> str:
    """items: [(entity_id, label, text)]；返回索引文件 sha256。"""
    import faiss  # 延迟导入：未安装时只影响向量召回，不影响图检索

    from app.llm import embedder

    vecs = embedder.embed([t for _, _, t in items])
    index = faiss.IndexFlatIP(vecs.shape[1])  # 向量已归一化：内积 = 余弦相似度
    index.add(vecs)
    d = index_dir(batch_id)
    d.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(d / "index.faiss"))
    meta = [{"entity_id": e, "label": lb, "text": t} for e, lb, t in items]
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return hashlib.sha256((d / "index.faiss").read_bytes()).hexdigest()


def search(batch_id: str, text: str, k: int) -> list[tuple[str, str, float]]:
    """返回 [(entity_id, label, score)]，同一实体只保留最高分。"""
    from app.llm import embedder

    d = index_dir(batch_id)
    index = _load_index(str(d / "index.faiss"))
    meta = _load_meta(str(d / "meta.json"))
    scores, idx = index.search(embedder.embed([text]), k * 3)
    best: dict[str, tuple[str, str, float]] = {}
    for score, i in zip(scores[0], idx[0], strict=False):
        if i < 0:
            continue
        m = meta[i]
        if m["entity_id"] not in best or score > best[m["entity_id"]][2]:
            best[m["entity_id"]] = (m["entity_id"], m["label"], float(score))
    return sorted(best.values(), key=lambda x: -x[2])[:k]


_cache: dict[str, object] = {}


def _load_index(path: str):
    import faiss

    if path not in _cache:
        _cache[path] = faiss.read_index(path)
    return _cache[path]


def _load_meta(path: str) -> list[dict]:
    key = path + "#meta"
    if key not in _cache:
        _cache[key] = json.loads(Path(path).read_text(encoding="utf-8"))
    return _cache[key]  # type: ignore[return-value]
