"""契约测试：mock、JSON Schema、Pydantic 类型、YAML 白名单之间必须一致。"""

import copy
import json
import typing

import pytest
from pydantic import ValidationError

from app.core.config import CONTRACTS_DIR, get_patterns, get_whitelist
from app.fixtures import MOCK_STATUSES, load_mock
from app.schemas.qa import NodeLabel, QAResponse, RelationType
from scripts import export_schema


def _raw(status: str) -> dict:
    return json.loads((CONTRACTS_DIR / "mocks" / f"{status}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("status", MOCK_STATUSES)
def test_mock_matches_contract(status):
    resp = load_mock(status)
    assert resp.status == status
    # 四种终态顶层键完全相同
    assert set(_raw(status)) == set(QAResponse.model_fields)


def test_error_mock_is_503_others_200():
    assert load_mock("error").http_status() == 503
    for s in ("success", "needs_context", "insufficient"):
        assert load_mock(s).http_status() == 200


def test_schema_file_up_to_date():
    current = (CONTRACTS_DIR / "qa_ask.schema.json").read_text(encoding="utf-8")
    assert current == export_schema.render(), "契约已变更，请执行 make schema 并提交"


def test_literals_match_whitelist():
    wl = get_whitelist()
    assert set(typing.get_args(NodeLabel)) == set(wl.nodes)
    assert set(typing.get_args(RelationType)) == set(wl.relations)


def test_patterns_follow_whitelist():
    wl = get_whitelist()
    for pid, p in get_patterns().patterns.items():
        assert 2 <= len(p.hops) <= 3, pid
        assert p.hops[0].from_label == p.anchor_label, pid
        assert p.hops[-1].to_label == p.target_label, pid
        for a, b in zip(p.hops, p.hops[1:], strict=False):
            assert a.to_label == b.from_label, f"{pid}: 跳与跳之间不连续"
        for h in p.hops:
            assert wl.allows(h.type, *h.stored), f"{pid}: {h.type} {h.stored} 不在白名单"


# ---- 关键约束必须被拦下 ----


def _bad(mutate) -> dict:
    d = copy.deepcopy(_raw("success"))
    mutate(d)
    return d


@pytest.mark.parametrize(
    "name,mutate",
    [
        ("引用未覆盖全部边", lambda d: d["claims"][0].update(citation_ids=["cit-1", "cit-2"])),
        ("graph_only 未标降级", lambda d: d.update(retrieval_mode="graph_only")),
        ("hop_count 与边数不符", lambda d: d["paths"][0].update(hop_count=2)),
        ("关系类型不在白名单", lambda d: d["paths"][0]["edges"][0].update(type="RELATED_TO")),
        ("success 无断言", lambda d: d.update(claims=[])),
        ("多余字段", lambda d: d.update(extra_field=1)),
    ],
)
def test_invariants_reject(name, mutate):
    with pytest.raises(ValidationError):
        QAResponse.model_validate(_bad(mutate))


def test_insufficient_must_not_have_claims():
    d = _raw("insufficient")
    d["claims"] = _raw("success")["claims"]
    with pytest.raises(ValidationError):
        QAResponse.model_validate(d)
