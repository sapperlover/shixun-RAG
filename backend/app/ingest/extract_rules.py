"""规则抽取（主力）：课程编码、学分表、先修课程、条款编号、方案-类别包含关系等。

输出写入待核验关系 CSV（data/relations/），字段见该目录下的表头。
关系类型与端点必须在 config/schema_whitelist.yaml 内，否则丢弃。

TODO(Data, D2)
"""

from __future__ import annotations

from app.ingest.chunk import Chunk


def extract(chunks: list[Chunk]) -> list[dict]:
    raise NotImplementedError
