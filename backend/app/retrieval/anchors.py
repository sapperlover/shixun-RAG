"""锚点匹配（V1.2 §4.2：解析 anchors；实体词典 + 可选 FAISS）。

输入：Intent、knowledge_batch。
输出：最多 retrieval.max_anchors 个 Anchor，按 score 降序。空列表 → pipeline 返回 ANCHOR_NOT_FOUND。

规则：先按名称/别名精确匹配；未命中再用 FAISS 向量相似度（≥ vector_anchor_min_score）。
FAISS 不可用时只用精确匹配，并让 Expansion 标记 graph_only 降级。

TODO(BE, D3)：实现真实匹配，并从 settings.yaml 的 stub_modules 中移除 "anchors"。
"""

from __future__ import annotations

from app import fixtures
from app.core.config import get_settings
from app.domain import Anchor, Intent


def match(intent: Intent, batch_id: str) -> list[Anchor]:
    if get_settings().is_stub("anchors"):
        n = fixtures.success().paths[0].nodes[0]
        return [Anchor(entity_id=n.node_id, label=n.label, name=n.name, score=1.0, match="exact")]
    raise NotImplementedError
