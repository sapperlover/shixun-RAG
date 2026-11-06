"""已实现的守卫逻辑：ID 规则、断言校验、批次切换、意图缺失字段。"""

import pytest

from app import fixtures
from app.answer import template, validate_claims
from app.domain import DraftClaim, FactRecord
from app.graph import ids
from app.retrieval import intent
from app.schemas.qa import Scope
from app.storage import snapshot, sqlite


def _facts() -> list[FactRecord]:
    mock = fixtures.success()
    cits = {c.relation_id: c for c in mock.citations}
    p = mock.paths[0]
    names = {n.node_id: n.name for n in p.nodes}
    return [
        FactRecord(
            f"f{i}",
            p.path_id,
            e.relation_id,
            names[e.from_],
            e.type,
            names[e.to],
            cits[e.relation_id],
        )
        for i, e in enumerate(p.edges)
    ]


def test_relation_id_deterministic_and_scope_sensitive():
    a = ids.relation_id("b1", "plan:x", "CONTAINS", "category:y", Scope(entry_year=2024))
    assert a == ids.relation_id("b1", "plan:x", "CONTAINS", "category:y", Scope(entry_year=2024))
    assert a != ids.relation_id("b1", "plan:x", "CONTAINS", "category:y", Scope(entry_year=2023))
    assert a != ids.relation_id("b2", "plan:x", "CONTAINS", "category:y", Scope(entry_year=2024))


def test_validate_accepts_mock_claim():
    claims = [DraftClaim(**c.model_dump()) for c in fixtures.success().claims]
    assert validate_claims.validate(claims, _facts()).ok


@pytest.mark.parametrize(
    "claim,reason",
    [
        (DraftClaim("c", "x", ["p-1"], ["cit-1"]), "未覆盖"),
        (DraftClaim("c", "x", ["p-1"], ["cit-9"]), "引用不存在"),
        (DraftClaim("c", "最多 12 学分", ["p-1"], ["cit-1", "cit-2", "cit-3"]), "数值"),
        (DraftClaim("c", "限选 4 门", ["p-1"], ["cit-1", "cit-2", "cit-3"]), "数值"),  # 2024 含 4
    ],
)
def test_validate_rejects(claim, reason):
    v = validate_claims.validate([claim], _facts())
    assert not v.kept and reason in v.dropped["c"]


def test_template_output_passes_validation():
    draft = template.render(_facts())
    assert draft.answer_mode == "template"
    assert validate_claims.validate(draft.claims, _facts()).ok


def test_intent_requires_scope_when_unknown_pattern():
    assert intent.parse("问题", Scope()).missing_fields == ["major_code", "entry_year"]
    assert intent.parse("问题", Scope(major_code="X", entry_year=2024)).missing_fields == []


def _add_batch(db: str, batch_id: str, state: str) -> None:
    with sqlite.connect(db) as conn:
        conn.execute(
            "INSERT INTO build_batches (batch_id, state, source_manifest_sha) VALUES (?, ?, 'x')",
            (batch_id, state),
        )


def test_switch_active_only_from_validated(tmp_path):
    db = str(tmp_path / "t.db")
    sqlite.migrate(db)
    _add_batch(db, "b1", "staging")
    _add_batch(db, "b2", "validated")
    with pytest.raises(ValueError):
        snapshot.switch_active("b1", db)
    assert snapshot.switch_active("b2", db) is None
    _add_batch(db, "b3", "validated")
    assert snapshot.switch_active("b3", db) == "b2"
    with sqlite.connect(db) as conn:
        states = dict(conn.execute("SELECT batch_id, state FROM build_batches").fetchall())
    assert states == {"b1": "staging", "b2": "retired", "b3": "active"}
