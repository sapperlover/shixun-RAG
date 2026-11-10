"""分块（V1.2 §4.1：Chunk 分割并记录页码/章节）。

按“第X条”等条款边界切分，表格整表一块；每块记录页码、章节、text_sha256，
chunk_id 用 app.graph.ids.chunk_id() 生成。

保留跨页表格，按明确章节及条款边界切分。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.graph import ids

_HEADING = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百零〇0-9]+[条章]|[一二三四五六七八九十]+、|附录\s*\d+\s*[：:])"
)
_TABLE = re.compile(r"课程编号|课程编码|积分计算分值|课程体系|学分数|总学时|支撑课程")


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
    """Split on real headings; never size-split a table or truncate a clause.

    Layout whitespace is retained. A table continuing on the next page stays in
    the same section until an explicit heading; long source blocks are intentional.
    Duplicate content uses the existing content-addressed ID and its first locator.
    """
    out = []
    lines: list[str] = []
    section = None
    first = last = None
    seen = set()

    def flush():
        nonlocal lines, first, last
        text = "\n".join(lines).strip()
        if text:
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            cid = ids.chunk_id(doc_id, doc_version, sha)
            if cid not in seen:
                out.append(Chunk(cid, doc_id, doc_version, first, last, section, text, sha))
                seen.add(cid)
        lines, first, last = [], None, None

    for page, text in pages:
        page_lines = text.splitlines()
        # Drop isolated printed page numbers at page edges, not numbers in table cells.
        nonblank = [i for i, line in enumerate(page_lines) if line.strip()]
        for i in [nonblank[0], nonblank[-1]] if nonblank else []:
            if re.fullmatch(r"\s*\d{1,3}\s*", page_lines[i]):
                page_lines[i] = ""
        in_table = bool(_TABLE.search(text))
        for line in page_lines:
            heading = _HEADING.match(line)
            # Numbered headings in a table cell must not split the table.
            is_clause = re.match(r"^\s*第[一二三四五六七八九十百零〇0-9]+条", line)
            if heading and (
                not in_table
                or is_clause
                or re.match(r"^\s*(?:附录|[一二三四五六七八九十]+、)", line)
            ):
                flush()
                section = line.strip() if not is_clause else is_clause.group().strip()
            if line.strip():
                if first is None:
                    first = page or None
                last = page or None
            lines.append(line.rstrip())
    flush()
    return out
