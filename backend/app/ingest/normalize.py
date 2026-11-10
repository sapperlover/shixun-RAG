"""实体别名归一：同一专业/课程/条款的不同写法映射到同一 entity_id（ID 格式见 schema_whitelist.yaml）。

读取可选 data/relations/aliases.csv 词典；无明确映射返回 None，不猜测实体 ID。
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from app.core.config import REPO_ROOT


def normalize_surface(surface: str) -> str:
    return re.sub(r"\s+", "", surface).replace("（", "(").replace("）", ")")


def canonical_entity_id(label: str, surface: str) -> str | None:
    path = Path(REPO_ROOT) / "data/relations/aliases.csv"
    if not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        matches = {
            row["entity_id"]
            for row in csv.DictReader(stream)
            if row["label"] == label
            and normalize_surface(row["surface"]) == normalize_surface(surface)
        }
    if len(matches) > 1:
        raise ValueError(f"Ambiguous alias for {label}: {surface}")
    return next(iter(matches), None)
