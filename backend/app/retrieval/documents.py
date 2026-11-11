"""Direct source retrieval for the full college corpus; no fabricated graph paths."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import ErrorCode, ServiceUnavailable
from app.schemas.qa import Scope
from app.storage import document_corpus

MAJOR_ALIASES = {
    "计算机科学与技术": ("计算机科学与技术", "计科"),
    "网络工程": ("网络工程", "网工"),
    "数据科学与大数据技术": ("数据科学与大数据技术", "大数据专业"),
    "软件工程": ("软件工程", "软工"),
}
GENERAL = set(
    document_corpus.tokens(
        "多少哪些什么如何是否可以需要规定要求学校学生本科专业学院课程学分培养方案年级"
        "北京邮电大学计算机科学与技术网络工程软件工程数据科学与大数据技术"
    )
)
RULE_WORDS = (
    "补考",
    "缓考",
    "重修",
    "缺考",
    "考场",
    "考核",
    "成绩管理",
    "学位",
    "撤销",
    "复核",
    "申辩",
    "迟到",
    "绩点",
)
PLAN_WORDS = ("培养方案", "学分", "必修", "选修", "课程", "学制", "毕业要求", "先修")


class DocumentScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    major_code: str | None = Field(default=None, max_length=64)
    entry_year: int | None = Field(default=None, ge=2000, le=2100)
    program_variant: Literal["regular", "international", "second_degree", "joint"] | None = None
    plan_revision: str | None = None
    college: str | None = None


def parse_scope(question: str, scope: Scope | dict | None) -> tuple[DocumentScope, list[str], bool]:
    if isinstance(scope, BaseModel):
        scope = scope.model_dump()
    selected = DocumentScope.model_validate(scope or {})
    years = set(map(int, re.findall(r"(20\d{2})\s*级", question)))
    mentioned = [
        major for major, aliases in MAJOR_ALIASES.items() if any(a in question for a in aliases)
    ]
    updates = {}
    missing = []
    if selected.entry_year is not None and years and selected.entry_year not in years:
        missing.append("entry_year")
    elif selected.entry_year is None and len(years) == 1:
        updates["entry_year"] = years.pop()
    elif len(years) > 1:
        missing.append("entry_year")
    if selected.major_code and mentioned and selected.major_code not in mentioned:
        missing.append("major_code")
    elif selected.major_code is None and len(mentioned) == 1:
        updates["major_code"] = mentioned[0]
    if selected.program_variant is None:
        if "普通本科" in question:
            updates["program_variant"] = "regular"
        elif "留学生" in question:
            updates["program_variant"] = "international"
        elif "第二学士" in question or "第二学位" in question:
            updates["program_variant"] = "second_degree"
        elif "会计学" in question or "联合学士" in question:
            updates["program_variant"] = "joint"
    selected = selected.model_copy(update=updates)
    institution = any(word in question for word in RULE_WORDS) and not any(
        word in question for word in ("学制", "培养方案")
    )
    curriculum = any(word in question for word in PLAN_WORDS) and not institution
    if curriculum:
        if selected.major_code is None:
            missing.append("major_code")
        if selected.entry_year is None:
            missing.append("entry_year")
    return selected, list(dict.fromkeys(missing)), institution


def _eligible(row: dict, selected: DocumentScope, institution: bool, question: str) -> bool:
    if row.get("is_toc") or re.search(r"\.{5,}|…{2,}", row["text"]):
        return False
    if row.get("needs_review"):
        return False  # Retain unreviewed source data offline, never silently surface corrupted OCR.
    if selected.college and selected.college not in (
        "计算机学院",
        "计算机学院（国家示范性软件学院）",
    ):
        return False
    if institution:
        if row["kind"] != "institution":
            return False
        if "学位" in question:
            return row["doc_id"] == "degree-rules"
        if any(
            word in question
            for word in ("补考", "缓考", "重修", "缺考", "迟到", "考核", "考场", "绩点")
        ):
            return row["doc_id"] == "assessment-rules"
        return True
    if row["kind"] == "institution":
        return not any(word in question for word in PLAN_WORDS)
    if selected.entry_year and row["book_year"] != selected.entry_year:
        return False
    if selected.plan_revision and row.get("plan_revision") != selected.plan_revision:
        return False
    if selected.major_code and row.get("major") not in (selected.major_code, None):
        return False
    # Shared appendices stay source excerpts, not invented per-major applicability edges.
    if (
        selected.major_code
        and row.get("major") is None
        and not any(w in question for w in ("附录", "英语", "体育", "创新实践", "创新创业"))
    ):
        return False
    if selected.program_variant and row.get("program_variant") not in (
        selected.program_variant,
        None,
    ):
        return False
    return selected.program_variant is not None or row.get("program_variant") in ("regular", None)


def retrieve_documents(question: str, scope: Scope | dict | None, request_id: str):
    from app.rag import RAGEvidence, RAGResult, retrieve_graph
    from app.schemas.qa import ErrorInfo, QARequest

    # Retain the old input length and year validation; only this independent interface gains extra scope fields.
    selected, missing, institution = parse_scope(question, scope)
    QARequest(question=question)
    if not question.strip() or not request_id.strip():
        raise ValueError("Question and request_id must not be blank")
    if missing:
        return RAGResult(
            request_id=request_id,
            status="needs_context",
            retrieval_type="document",
            missing_fields=missing,
        )
    if (
        not institution
        and selected.major_code == "计算机科学与技术"
        and selected.entry_year == 2024
        and selected.program_variant in (None, "regular")
        and any(
            name in question
            for name in (
                "通识教育课程",
                "学科基础课程",
                "专业基础课程",
                "专业课程",
                "实践教学",
                "创新实践",
            )
        )
    ):
        graph = retrieve_graph(
            question, {"major_code": selected.major_code, "entry_year": 2024}, request_id
        )
        # A broken graph path must not silently become a successful multi-hop answer.
        return graph.model_copy(update={"resolved_scope": selected.model_dump()})
    batch = None
    try:
        batch = document_corpus.active()
        if batch is None:
            raise ServiceUnavailable(
                ErrorCode.NO_ACTIVE_BATCH, "Initialize the document corpus first"
            )
        source = document_corpus.rows(batch)
        eligible = {
            r["chunk_id"]: r for r in source if _eligible(r, selected, institution, question)
        }
        lexical = [cid for cid in document_corpus.keyword(batch, question) if cid in eligible]
        degraded = False
        try:
            vector = [
                (cid, score)
                for cid, score in document_corpus.vector(batch, question)
                if cid in eligible
            ]
        except Exception:
            vector = []
            degraded = True
        scores = {}
        vector_scores = dict(vector)
        for weight, ids in ((1.0, lexical), (0.8, [cid for cid, _ in vector])):
            for rank, cid in enumerate(ids, 1):
                scores[cid] = scores.get(cid, 0) + weight / (60 + rank)
        query_terms = set(document_corpus.tokens(question)) - GENERAL
        ranked = []
        seen_pages = set()
        for cid in sorted(scores, key=lambda c: -scores[c]):
            row = eligible[cid]
            overlap = query_terms & set(document_corpus.tokens(row["text"]))
            if not overlap and vector_scores.get(cid, 0) < 0.70:
                continue
            if (
                not institution
                and not any(word in question for word in PLAN_WORDS)
                and len(overlap) < 2
                and vector_scores.get(cid, 0) < 0.70
            ):
                continue  # One incidental word is not support for an otherwise out-of-domain question.
            page_key = (row["doc_id"], row["page_start"])
            if page_key in seen_pages:
                continue
            seen_pages.add(page_key)
            ranked.append((row, scores[cid]))
            if len(ranked) == 4:
                break
        common = {
            "request_id": request_id,
            "retrieval_type": "document",
            "knowledge_batch": batch,
            "retrieval_mode": "keyword_only" if degraded else "hybrid",
            "degraded_mode": degraded,
            "degradation_reason": "document_vector_unavailable" if degraded else None,
            "resolved_scope": selected.model_dump(),
            "warnings": ["source_retrieval_is_not_confirmation_of_rule_applicability"],
        }
        if not ranked:
            return RAGResult(
                **common,
                status="insufficient",
                error=ErrorInfo(code=ErrorCode.ANCHOR_NOT_FOUND, retryable=False),
            )
        evidence = []
        for row, score in ranked:
            evidence.append(
                RAGEvidence(
                    citation_id="doc-cit-"
                    + hashlib.sha256(f"{batch}|{row['chunk_id']}".encode()).hexdigest()[:16],
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    doc_version=row["doc_version"],
                    doc_title=row["title"],
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    section=row["section"],
                    text=row["text"],
                    source_kind=row["source_kind"],
                    verification_status=row["verification_status"],
                    needs_review=row["needs_review"],
                    verified_by=row.get("verified_by"),
                    scope_verified=False,
                    source_file=row["source_file"],
                    source_sha256=row["source_sha256"],
                    entry_year=row.get("entry_year"),
                    major=row.get("major"),
                    program_variant=row.get("program_variant"),
                    book_year=row.get("book_year"),
                    plan_revision=row.get("plan_revision"),
                    score=score,
                    verification_note=row["scope_note"],
                )
            )
        return RAGResult(**common, status="success", evidence=evidence)
    except ServiceUnavailable as exc:
        return RAGResult(
            request_id=request_id,
            status="error",
            retrieval_type="document",
            knowledge_batch=batch,
            error=ErrorInfo(code=exc.code, retryable=True),
        )
    except (sqlite3.Error, OSError):
        return RAGResult(
            request_id=request_id,
            status="error",
            retrieval_type="document",
            knowledge_batch=batch,
            error=ErrorInfo(code=ErrorCode.METADATA_UNAVAILABLE, retryable=True),
        )
