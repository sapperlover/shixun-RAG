"""规则抽取（主力）：课程编码、学分表、先修课程、条款编号、方案-类别包含关系等。

输出为字面观察与待核验候选；scripts.prepare_rag 组装现有知识包关系CSV。
不推断先修关系，不自动核验候选。
"""

from __future__ import annotations

import re

from app.ingest.chunk import Chunk
from app.ingest.normalize import normalize_surface

# Only literal categories in the source can become candidates.
CATEGORIES = (
    "通识教育课程",
    "专业教育课程",
    "学科基础课程",
    "专业基础课程",
    "专业课程",
    "实践教学",
    "创新实践",
    "思想政治理论课",
    "语言类",
    "自然科学类",
    "体育类",
    "素质拓展课",
)


def extract(chunks: list[Chunk]) -> list[dict]:
    """Literal category/rule/course observations, not verified graph assertions.

    Returning observations keeps the existing list[dict] interface; packaging a
    category's normative text into a CITES candidate requires explicit human review.
    Semester order, course maps and general course knowledge never imply prerequisites.
    """
    out = []
    for chunk in chunks:
        compact = normalize_surface(chunk.text)
        categories = [name for name in CATEGORIES if name in compact]
        for name in categories:
            out.append({"kind": "category", "name": name, "chunk_id": chunk.chunk_id})
            if re.search(r"学分|必修|选修|认定|成绩|要求", compact):
                out.append(
                    {
                        "kind": "category_rule_candidate",
                        "name": name,
                        "chunk_id": chunk.chunk_id,
                        "requires_review": True,
                    }
                )
        # Layout extraction separates name and numeric cells by multiple spaces.
        for line in chunk.text.splitlines():
            match = re.search(r"(?<!\d)(\d{10})\s+(.+?)\s{2,}(\d+(?:\.\d+)?)\s", line)
            if match:
                name = re.sub(r"[#*&⌃^]", "", match[2]).strip()
                if name and not re.fullmatch(r"[\d\s.]+", name):
                    out.append(
                        {
                            "kind": "course",
                            "code": match[1],
                            "name": name,
                            "chunk_id": chunk.chunk_id,
                        }
                    )
    return out
