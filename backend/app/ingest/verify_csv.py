"""P0 人工预核验 CSV 的读写（V1.2 §1.3、附录 B.2）。

流程：数据工程师生成知识包里的 relations.csv → 核验人对照原文逐边填写
verification_status / verified_by / verified_at → 构建批次时只有 verified 的边参与检索。
"""

from __future__ import annotations

import csv
from pathlib import Path

# relation_id 不在表中：它依赖 batch_id，由构建批次时用 app.graph.ids.relation_id() 生成。
COLUMNS = [
    "type",
    "from_entity_id",
    "from_label",
    "to_entity_id",
    "to_label",
    "major_code",
    "entry_year",
    "evidence_chunk_ids",
    "evidence_excerpt",
    "confidence",
    "source",
    "verification_status",
    "verified_by",
    "verified_at",
    "note",
]


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"表头与契约不一致：{reader.fieldnames}")
        return list(reader)
