"""实体别名归一：同一专业/课程/条款的不同写法映射到同一 entity_id（ID 格式见 schema_whitelist.yaml）。

TODO(Data, D2)：维护 data/relations/aliases.csv 词典并实现。
"""

from __future__ import annotations


def canonical_entity_id(label: str, surface: str) -> str | None:
    raise NotImplementedError
