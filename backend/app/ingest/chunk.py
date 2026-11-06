"""分块（文档-2 §4.2(1) 第 2 步）。

按“第X条”等条款边界切分，表格整表一块；每块记录页码、章节、text_sha256，
chunk_id 用 app.graph.ids.chunk_id() 生成。

TODO(Data, D2)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_version: str
    page_start: int | None
    page_end: int | None
    section: str | None
    text: str
    text_sha256: str


def split(doc_id: str, doc_version: str, pages: list[tuple[int, str]]) -> list[Chunk]:
    raise NotImplementedError
