"""逐跳扩展（V1.2 §4.2；文档-2 §4.2(2) 第 3 步）。

输入：锚点、Intent、knowledge_batch。
输出：Expansion（候选路径、跳级日志、断在第几跳、检索模式）。

规则：
- 每跳一条 Cypher，只走白名单内、verified=true、batch_id 等于本次批次、适用于该年级的边；
- 每跳保留 per_hop_candidates 个候选，全局不超过 max_paths 条，最多 max_hops 跳；
- 每跳的候选数、保留数和剪枝原因写入 HopLogEntry（失败归因依赖它）；
- 第 k 跳无结果 → failed_hop=k。

查询模板见 V1.2 附录 A.3。

TODO(BE, D3)：实现，并从 stub_modules 中移除 "expand"。
"""

from __future__ import annotations

from app import fixtures
from app.core.config import get_settings
from app.domain import Anchor, CandidatePath, EdgeEvidence, Expansion, HopLogEntry, Intent


def expand(anchors: list[Anchor], intent: Intent, batch_id: str) -> Expansion:
    if get_settings().is_stub("expand"):
        mock = fixtures.success()
        path = mock.paths[0]
        cits = {c.relation_id: c for c in mock.citations}
        evidence = [
            EdgeEvidence(
                relation_id=e.relation_id,
                verified=True,
                evidence_chunk_ids=[cits[e.relation_id].chunk_id],
                batch_id=batch_id,
            )
            for e in path.edges
        ]
        log = [HopLogEntry(hop=i + 1, candidates_in=1, kept=1) for i in range(path.hop_count)]
        return Expansion(
            candidates=[CandidatePath(path=path, pattern="T2", evidence=evidence)],
            hop_log=log,
            retrieval_mode=mock.retrieval_mode or "hybrid",
        )
    raise NotImplementedError
