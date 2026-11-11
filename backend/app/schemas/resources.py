"""文档、证据、反馈、评测接口的数据结构。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.qa import Scope

# ---------- 文档 ----------

PublishState = Literal["draft", "published", "archived"]


class DocumentOut(BaseModel):
    doc_id: str
    doc_version: str
    title: str
    source_uri: str
    file_sha256: str
    access_level: Literal["public", "restricted"]
    publish_state: PublishState
    scope: Scope
    created_at: str
    knowledge_batch: str | None = None


# ---------- 证据读回 ----------


class EvidenceOut(BaseModel):
    """GET /evidence/{citation_id}?knowledge_batch=... 返回的原文块。"""

    citation_id: str
    knowledge_batch: str
    relation_id: str | None
    chunk_id: str
    doc_id: str
    doc_title: str
    doc_version: str
    section: str | None
    page_start: int | None
    page_end: int | None
    text: str
    verification_status: str


# ---------- 反馈 ----------

FeedbackType = Literal["helpful", "wrong_answer", "citation_invalid", "unresolved"]


class FeedbackIn(BaseModel):
    request_id: str
    type: FeedbackType
    comment: str | None = Field(default=None, max_length=500)


# ---------- 评测（V1.2 附录 D.1）----------

ExpectedStatus = Literal["success", "needs_context", "insufficient"]
FailureStage = Literal[
    "first_hop_miss",
    "later_hop_missing",
    "version_conflict",
    "citation_missing",
    "model_misuse",
    "justified_refusal",
]


class GoldEdge(BaseModel):
    from_: str = Field(alias="from")
    type: str
    to: str

    model_config = {"populate_by_name": True}


class EvalQuestion(BaseModel):
    """questions_v1.jsonl 每行一题。key_points 为本项目扩展字段（见 ADR-008）。"""

    question_id: str
    question: str
    scope: Scope
    gold_answer: str
    key_points: list[str] = Field(default_factory=list)
    gold_relation_path: list[GoldEdge]
    hop_count: int = Field(ge=0, le=3)
    doc_version: str
    expected_status: ExpectedStatus
    source_evidence_ids: list[str] = Field(default_factory=list)


class EvalRecord(BaseModel):
    """records.jsonl 每行一题的结果。"""

    question_id: str
    request_id: str
    batch_id: str | None
    status: str
    predicted_path: list[GoldEdge]
    path_hit: bool
    answer_correct: bool
    citation_covered: int  # 有可读回来源的关键断言数
    claims_total: int  # 关键断言总数
    failure_stage: FailureStage | None
    elapsed_ms: int
    question: str = ""
    answer: str | None = None
    answer_mode: str | None = None
    expected_status: str = "success"
    hop_count: int = 0
    response: dict = Field(default_factory=dict)
    hop_log: list[dict] = Field(default_factory=list)


class EvalMetrics(BaseModel):
    questions: int
    path_hit_rate: float | None
    answer_accuracy: float | None
    citation_coverage: float | None  # 无断言时为 None（N/A）
    failure_distribution: dict[str, int]
    two_hop_path_hit_rate: float | None = None
    three_hop_path_hit_rate: float | None = None
    api_answer_rate: float | None = None
    average_latency_ms: float | None = None
    p95_latency_ms: int | None = None


class EvalRunIn(BaseModel):
    dataset_sha256: str = Field(description="必须与冻结文件的哈希一致，否则拒绝运行")


class EvalRunOut(BaseModel):
    run_id: str
    status: Literal["running", "finished", "failed"]
    dataset_sha256: str
    scorer_version: str
    git_commit: str
    batch_id: str | None
    metrics: EvalMetrics | None
    created_at: str
    error_detail: str | None = None
