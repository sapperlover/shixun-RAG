"""路径 → 可核验事实（V1.2 §4.3）。

输入：排序后的路径、knowledge_batch。
输出：FactRecord 列表：一条边对应一条事实和一个 Citation。
Citation 的原文摘录必须按本次 batch 从 SQLite chunks 表读出，不能由模型生成。

TODO(BE, D3)：按 relation_evidence/chunks 读取原文，并从 stub_modules 中移除 "facts"。
"""

from __future__ import annotations

from app import fixtures
from app.core.config import get_settings
from app.domain import CandidatePath, FactRecord


def build(paths: list[CandidatePath], batch_id: str) -> list[FactRecord]:
    if get_settings().is_stub("facts"):
        cits = {c.relation_id: c for c in fixtures.success().citations}
        out: list[FactRecord] = []
        for cp in paths:
            names = {n.node_id: n.name for n in cp.path.nodes}
            for e in cp.path.edges:
                out.append(
                    FactRecord(
                        fact_id=f"fact-{len(out) + 1}",
                        path_id=cp.path.path_id,
                        relation_id=e.relation_id,
                        subject=names[e.from_],
                        predicate=e.type,
                        object=names[e.to],
                        citation=cits[e.relation_id],
                    )
                )
        return out
    raise NotImplementedError
