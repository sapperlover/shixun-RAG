"""Frozen retrieval-only evaluation. No answer-correctness score is produced."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.rag import retrieve
from app.schemas.qa import Scope
from app.schemas.resources import GoldEdge


class RetrievalQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    question: str
    scope: Scope
    expected_status: Literal["success", "needs_context", "insufficient", "error"]
    gold_relation_path: list[GoldEdge]
    source_evidence_ids: list[str]
    hop_count: int = Field(ge=0, le=3)
    review_status: Literal["verified"]
    reviewed_by: str = Field(min_length=1)
    doc_version: str

    @model_validator(mode="after")
    def _gold(self):
        if self.expected_status == "success" and (
            self.hop_count not in (2, 3)
            or len(self.gold_relation_path) != self.hop_count
            or not self.source_evidence_ids
            or not self.doc_version.strip()
        ):
            raise ValueError("success requires reviewed 2/3-hop gold path, version and sources")
        return self


def load(path: Path, sha256: str) -> list[RetrievalQuestion]:
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        raise ValueError("Frozen retrieval dataset checksum mismatch")
    rows = [
        RetrievalQuestion.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len({q.question_id for q in rows}) != len(rows):
        raise ValueError("Duplicate question IDs")
    return rows


def run(questions: list[RetrievalQuestion], *, retriever=None) -> dict:
    retriever = retriever or retrieve
    records = []
    for q in questions:
        start = time.perf_counter()
        result = retriever(q.question, q.scope, "rag-eval-" + q.question_id)
        gold = {(e.from_, e.type, e.to) for e in q.gold_relation_path}
        hit = any({(e.from_, e.type, e.to) for e in p.edges} == gold for p in result.paths)
        if q.expected_status != "success":
            hit = result.status == q.expected_status
        expected_sources = set(q.source_evidence_ids)
        observed_sources = {s.chunk_id for s in result.evidence}
        records.append(
            dict(
                question_id=q.question_id,
                status=result.status,
                expected_status=q.expected_status,
                knowledge_batch=result.knowledge_batch,
                path_hit=hit,
                status_match=result.status == q.expected_status,
                gold_evidence_hit=bool(expected_sources) and expected_sources <= observed_sources,
                failed_hop=result.error.failed_hop if result.error else None,
                error_code=result.error.code if result.error else None,
                elapsed_ms=round((time.perf_counter() - start) * 1000),
                predicted_paths=[p.model_dump(by_alias=True) for p in result.paths],
            )
        )
    success = [r for r in records if r["expected_status"] == "success"]
    negative = [r for r in records if r["expected_status"] != "success"]
    return dict(
        dataset_reviewers=sorted({q.reviewed_by for q in questions}),
        contains_ai_reviewed_questions=any(q.reviewed_by.startswith("codex-ai") for q in questions),
        answer_evaluation="not_performed",
        questions=len(success),
        path_hit_rate=sum(r["path_hit"] for r in success) / len(success) if success else None,
        gold_evidence_hit_rate=sum(r["gold_evidence_hit"] for r in success) / len(success)
        if success
        else None,
        negative_questions=len(negative),
        negative_status_matches=sum(r["status_match"] for r in negative),
        records=records,
    )
