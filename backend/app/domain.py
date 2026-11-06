"""模块之间传递的内部数据结构（不对外暴露）。★ 冻结契约：改字段需架构师同意。

数据流：
  Intent ──anchors.match──▶ list[Anchor] ──expand.expand──▶ Expansion(candidates, hop_log)
        ──path_check.filter_complete──▶ list[CandidatePath] ──rank.rank──▶ list[CandidatePath]
        ──facts.build──▶ list[FactRecord] ──generate.generate──▶ Draft
        ──validate_claims.validate──▶ Validation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.schemas.qa import Citation, Path, Scope

PatternId = Literal["T1", "T2", "T3"]


@dataclass(frozen=True)
class Intent:
    question: str
    scope: Scope
    pattern: PatternId | None  # None = 尚未识别题型
    mentions: list[str] = field(default_factory=list)  # 问题中的实体词/关键词
    missing_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Anchor:
    entity_id: str
    label: str
    name: str
    score: float
    match: Literal["exact", "alias", "vector"]


@dataclass
class HopLogEntry:
    """跳级日志（V1.2 §4.3 记录断链跳次、§6.1 失败分析）：每跳候选数、保留数、剪枝原因 → 失败归因的依据。"""

    hop: int
    candidates_in: int
    kept: int
    pruned: dict[str, int] = field(default_factory=dict)  # 原因 → 数量


@dataclass
class EdgeEvidence:
    relation_id: str
    verified: bool
    evidence_chunk_ids: list[str]
    batch_id: str


@dataclass
class CandidatePath:
    path: Path  # 对外展示用的节点/边
    pattern: PatternId | None
    evidence: list[EdgeEvidence]  # 与 path.edges 一一对应
    score: float = 0.0


@dataclass
class Expansion:
    candidates: list[CandidatePath]
    hop_log: list[HopLogEntry]
    failed_hop: int | None = None  # 第几跳无结果；None = 未断链
    retrieval_mode: Literal["hybrid", "graph_only"] = "hybrid"
    degradation_reason: str | None = None


@dataclass(frozen=True)
class FactRecord:
    """可核验事实（V1.2 §4.3）：一条边 = 一条事实 = 一个引用。"""

    fact_id: str
    path_id: str
    relation_id: str
    subject: str
    predicate: str
    object: str
    citation: Citation


@dataclass
class DraftClaim:
    claim_id: str
    text: str
    path_ids: list[str]
    citation_ids: list[str]


@dataclass
class Draft:
    answer: str
    claims: list[DraftClaim]
    answer_mode: Literal["llm", "template"]
    degradation_reason: str | None = None


@dataclass
class Validation:
    kept: list[DraftClaim]
    dropped: dict[str, str]  # claim_id → 原因

    @property
    def ok(self) -> bool:
        return not self.dropped
