"""LLM 辅助抽取（补充）：条款之间的“引用 / 适用”关系，以 JSON 输出。

关系必须在白名单内；evidence 必须是原文子串，否则丢弃；置信度 < ingest.relation_min_confidence
的只进入待核验清单，不得建议通过。

TODO(Data, D2，可选)
"""

from __future__ import annotations

from app.ingest.chunk import Chunk


def extract(chunks: list[Chunk]) -> list[dict]:
    raise NotImplementedError
