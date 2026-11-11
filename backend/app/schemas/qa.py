"""POST /qa/ask 契约（V1.2 附录 C）。★ 冻结契约：修改需架构师同意，并执行 `make schema`。

四种业务终态返回相同的顶层键。模型级校验把 V1.2 的强制约束写成代码，
任何模块拼出的响应只要违反约束，就会在序列化前被拦下（契约测试也依赖这些校验）：
- 路径：hop_count == 边数 ∈ [2, 3]，节点数 = 边数 + 1，标签/关系类型在白名单内，边端点必须在节点中；
- 可核验（附录 B.3）：每条 claim 的 citation 覆盖其依赖路径的每一条 relation_id；
- 降级可见：retrieval_mode=graph_only 或 answer_mode=template 时 degraded_mode 必须为 true；
- 终态一致性：success 必须有路径和断言；needs_context 必须有 missing_fields；insufficient 不得有断言；
  error 不得有路径、断言和引用。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import ErrorCode

Status = Literal["success", "needs_context", "insufficient", "error"]
ScopeField = Literal["major_code", "entry_year", "program_variant"]
NodeLabel = Literal[
    "College", "Professional", "ProgramPlan", "CourseCategory", "Course", "RuleClause"
]
RelationType = Literal["BELONGS_TO", "CONTAINS", "APPLIES_TO", "CITES", "PREREQUISITE_OF"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ---------- 请求 ----------


class Scope(_Strict):
    major_code: str | None = Field(default=None, max_length=32)
    entry_year: int | None = Field(default=None, ge=2000, le=2100)
    program_variant: Literal["regular", "international", "second_degree", "joint"] | None = None
    plan_revision: str | None = None
    college: str | None = None


class QARequest(_Strict):
    question: str = Field(min_length=1, max_length=500)
    scope: Scope = Field(default_factory=Scope)
    session_id: str | None = Field(default=None, max_length=64, description="FR-07 预留")


# ---------- 响应组成 ----------


class PathNode(_Strict):
    node_id: str = Field(description="业务实体 ID（entity_id），不含 batch 前缀")
    label: NodeLabel
    name: str


class PathEdge(_Strict):
    relation_id: str
    type: RelationType
    from_: str = Field(alias="from", description="起点 node_id（存储方向）")
    to: str = Field(description="终点 node_id（存储方向）")


class Path(_Strict):
    path_id: str
    hop_count: int = Field(ge=2, le=3)
    nodes: list[PathNode]
    edges: list[PathEdge]

    @model_validator(mode="after")
    def _shape(self) -> Path:
        if len(self.edges) != self.hop_count:
            raise ValueError(
                f"{self.path_id}: hop_count={self.hop_count} 与边数 {len(self.edges)} 不符"
            )
        if len(self.nodes) != self.hop_count + 1:
            raise ValueError(f"{self.path_id}: 节点数应为 hop_count+1")
        ids = {n.node_id for n in self.nodes}
        for e in self.edges:
            if e.from_ not in ids or e.to not in ids:
                raise ValueError(f"{self.path_id}: 边 {e.relation_id} 的端点不在节点列表中")
        return self


class Claim(_Strict):
    claim_id: str
    text: str
    path_ids: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(min_length=1)


class Citation(_Strict):
    citation_id: str
    relation_id: str | None
    chunk_id: str
    doc_id: str
    doc_version: str
    section: str | None = None
    page: int | None = None
    excerpt: str
    doc_title: str | None = None


class ErrorInfo(_Strict):
    code: ErrorCode
    failed_hop: int | None = Field(default=None, ge=1, le=3)
    retryable: bool


# ---------- 响应 ----------


class QAResponse(_Strict):
    request_id: str
    status: Status
    knowledge_batch: str | None
    retrieval_mode: Literal["hybrid", "graph_only", "keyword_only"] | None
    retrieval_type: Literal["graph", "document"] = "graph"
    warnings: list[str] = Field(default_factory=list)
    resolved_scope: Scope | None = None
    hop_log: list[dict] = Field(default_factory=list)
    degraded_mode: bool
    degradation_reason: str | None
    answer_mode: Literal["llm", "template"] | None
    answer: str | None
    claims: list[Claim]
    paths: list[Path]
    citations: list[Citation]
    missing_fields: list[ScopeField]
    error: ErrorInfo | None

    @model_validator(mode="after")
    def _invariants(self) -> QAResponse:
        s = self.status
        if (
            self.retrieval_mode in ("graph_only", "keyword_only") or self.answer_mode == "template"
        ) and not (self.degraded_mode):
            raise ValueError("graph_only / template 时 degraded_mode 必须为 true")
        if self.degraded_mode and not self.degradation_reason:
            raise ValueError("degraded_mode=true 时必须给出 degradation_reason")

        if s == "success":
            if not (self.claims and self.citations):
                raise ValueError("success 必须包含 claims、citations")
            if self.retrieval_type == "graph" and not self.paths:
                raise ValueError("多跳回答必须包含真实图路径")
            if self.retrieval_type == "document" and self.paths:
                raise ValueError("原文检索不得伪造图路径")
            if self.error is not None or self.missing_fields:
                raise ValueError("success 不应包含 error / missing_fields")
            if not (self.knowledge_batch and self.retrieval_mode and self.answer_mode):
                raise ValueError("success 必须给出 knowledge_batch、retrieval_mode、answer_mode")
            if not self.answer:
                raise ValueError("success 必须有 answer")
        elif s == "needs_context":
            if not self.missing_fields:
                raise ValueError("needs_context 必须给出 missing_fields")
            if self.claims or self.paths or self.citations:
                raise ValueError("needs_context 不应包含 claims/paths/citations")
        elif s == "insufficient":
            if self.claims:
                raise ValueError("insufficient 不得包含 claims（不给确定性结论）")
            if self.error is None:
                raise ValueError("insufficient 必须在 error 中说明断链原因")
        elif s == "error":
            if self.error is None:
                raise ValueError("error 必须包含 error")
            if self.claims or self.paths or self.citations:
                raise ValueError("error 不应包含 claims/paths/citations")

        self._check_traceability()
        return self

    def _check_traceability(self) -> None:
        """附录 B.3「可核验」：claim 的引用覆盖其依赖路径的每一条边。"""
        paths = {p.path_id: p for p in self.paths}
        cits = {c.citation_id: c for c in self.citations}
        for claim in self.claims:
            if self.retrieval_type == "graph" and not claim.path_ids:
                raise ValueError("多跳结论必须关联图路径")
            if self.retrieval_type == "document" and claim.path_ids:
                raise ValueError("原文回答不得引用不存在的图路径")
            missing_p = [pid for pid in claim.path_ids if pid not in paths]
            missing_c = [cid for cid in claim.citation_ids if cid not in cits]
            if missing_p or missing_c:
                raise ValueError(
                    f"{claim.claim_id} 引用了不存在的路径 {missing_p} 或引用 {missing_c}"
                )
            covered = {cits[cid].relation_id for cid in claim.citation_ids}
            for pid in claim.path_ids:
                need = {e.relation_id for e in paths[pid].edges}
                if not need <= covered:
                    raise ValueError(
                        f"{claim.claim_id} 的引用未覆盖 {pid} 的边 {sorted(need - covered)}"
                    )

    # ---- 构造辅助：各模块统一用这些方法拼终态，避免漏键 ----

    @classmethod
    def needs_context(cls, request_id: str, batch: str | None, missing: list[str]) -> QAResponse:
        base = _empty(request_id, "needs_context", batch)
        base["missing_fields"] = missing
        return cls(**base)

    @classmethod
    def insufficient(
        cls,
        request_id: str,
        batch: str,
        code: ErrorCode,
        failed_hop: int | None = None,
        *,
        retrieval_mode: str | None = None,
        degradation_reason: str | None = None,
        paths: list[Path] | None = None,
        citations: list[Citation] | None = None,
    ) -> QAResponse:
        base = _empty(request_id, "insufficient", batch)
        base.update(
            retrieval_mode=retrieval_mode,
            degraded_mode=degradation_reason is not None,
            degradation_reason=degradation_reason,
            paths=paths or [],
            citations=citations or [],
            error=ErrorInfo(code=code, failed_hop=failed_hop, retryable=False),
        )
        return cls(**base)

    @classmethod
    def service_error(
        cls, request_id: str, code: ErrorCode, batch: str | None = None
    ) -> QAResponse:
        base = _empty(request_id, "error", batch)
        base["error"] = ErrorInfo(code=code, failed_hop=None, retryable=True)
        return cls(**base)

    def http_status(self) -> int:
        return 503 if self.status == "error" else 200


def _empty(request_id: str, status: str, batch: str | None) -> dict:
    return {
        "request_id": request_id,
        "status": status,
        "knowledge_batch": batch,
        "retrieval_mode": None,
        "degraded_mode": False,
        "degradation_reason": None,
        "answer_mode": None,
        "answer": None,
        "claims": [],
        "paths": [],
        "citations": [],
        "missing_fields": [],
        "error": None,
    }
