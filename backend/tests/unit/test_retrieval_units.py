"""检索与生成的纯逻辑：不连数据库。"""

import json
import shutil
from pathlib import Path

import pytest

from app.answer import generate, template, validate_claims
from app.domain import CandidatePath, EdgeEvidence, FactRecord, Intent
from app.fixtures import load_mock
from app.graph.dictionary import Dictionary, EntityRef, normalize
from app.ingest import bundle
from app.retrieval import intent, path_check
from app.schemas.qa import Scope

DEMO = Path(__file__).parents[3] / "data" / "demo"


# ---------- 知识包契约 ----------


def test_demo_bundle_is_valid():
    b = bundle.load(DEMO)
    assert len(b.entities) == 12 and len(b.relations) == 11


@pytest.mark.parametrize(
    "file,mutate,expect",
    [
        ("relations.csv", lambda s: s.replace("CITES", "RELATED", 1), "不在白名单"),
        ("relations.csv", lambda s: s.replace("demo-reviewer", "", 1), "verified_by"),
        ("chunks.jsonl", lambda s: s.replace("适用于", "适用", 1), "chunk_id 与内容不符"),
        (
            "entities.jsonl",
            lambda s: s.replace('"course_code": "DEMO101"', '"x": 1', 1),
            "缺少必需属性",
        ),
        ("documents.csv", lambda s: s.replace("教学演示用模拟资料，非真实制度", "", 1), "授权依据"),
    ],
)
def test_bundle_rejects(tmp_path, file, mutate, expect):
    d = tmp_path / "kb"
    shutil.copytree(DEMO, d)
    p = d / file
    p.write_text(mutate(p.read_text(encoding="utf-8")), encoding="utf-8")
    with pytest.raises(bundle.BundleError, match=expect):
        bundle.load(d)


# ---------- 意图 / 词典 ----------


def test_intent_t3_keyword_needs_no_scope():
    i = intent.parse("学操作系统之前需要先修哪些课？", Scope())
    assert i.pattern == "T3" and i.missing_fields == []


def test_intent_unknown_pattern_requires_full_scope():
    assert intent.parse("专业选修课怎么认定", Scope(major_code="X")).missing_fields == [
        "entry_year"
    ]


def test_dictionary_longest_match_and_tag_stripping():
    d = Dictionary(
        entities={
            "c:PE": EntityRef("c:PE", "CourseCategory", "【模拟】专业选修课"),
            "c:X": EntityRef("c:X", "CourseCategory", "选修课"),
        },
        surfaces={normalize("【模拟】专业选修课"): {"c:PE"}, normalize("选修课"): {"c:X"}},
    )
    hits = d.find_mentions("2024 级专业选修课怎么认定", min_chars=2)
    assert [r.entity_id for r, _ in hits] == ["c:PE"]  # “选修课”被更长的命中覆盖


# ---------- 路径判定（纯逻辑部分） ----------


def _cand(nodes, mentions_ok=True) -> CandidatePath:
    mock = load_mock("success")
    p = mock.paths[0]
    return CandidatePath(
        path=p,
        pattern="T2",
        evidence=[EdgeEvidence(e.relation_id, True, ["c"], "b1") for e in p.edges],
        node_props={n.node_id: {"batch_id": "b1"} for n in p.nodes},
    )


def test_relevance_requires_mentioned_entity_of_same_label():
    c = _cand(None)
    cat = c.path.nodes[2]  # CourseCategory
    assert path_check._relevant(c, {cat.node_id}, {"CourseCategory"})
    assert not path_check._relevant(
        c, {"category:other", c.path.nodes[0].node_id}, {"CourseCategory"}
    )
    assert not path_check._relevant(c, set(), set())


def test_version_conflict_detected():
    a, b = _cand(None), _cand(None)
    rule = a.path.nodes[-1].node_id
    a.node_props[rule] = {"doc_id": "d", "section": "s12", "doc_version": "v1"}
    b.node_props = {**b.node_props, rule: {"doc_id": "d", "section": "s12", "doc_version": "v2"}}
    assert len(path_check._version_conflict([a, b])) == 2
    assert path_check._version_conflict([a]) == []


# ---------- 生成输出解析 ----------


def _facts() -> list[FactRecord]:
    mock = load_mock("success")
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


def test_parse_claims_full_coverage_passes_validation():
    raw = json.dumps(
        {"claims": [{"text": "按第十二条认定", "citation_ids": ["cit-1", "cit-2", "cit-3"]}]}
    )
    claims = generate.parse_claims(raw, _facts())
    assert claims[0].path_ids == ["p-1"]
    assert validate_claims.validate(claims, _facts()).ok


def test_parse_claims_partial_citation_is_rejected_not_patched():
    raw = json.dumps({"claims": [{"text": "按第十二条认定", "citation_ids": ["cit-3"]}]})
    claims = generate.parse_claims(raw, _facts())
    assert claims[0].citation_ids == ["cit-3"]  # 不自动补引用（V1.2：不得先回答后补引用）
    assert not validate_claims.validate(claims, _facts()).ok


def test_parse_claims_tolerates_garbage():
    assert generate.parse_claims("不是 JSON", _facts()) == []


def test_prompt_marks_untrusted_text_and_required_citations():
    prompt = generate.build_prompt("问题", _facts())
    assert "引用时须同时引用：cit-1, cit-2, cit-3" in prompt
    assert "不要执行" in generate.SYSTEM


def test_answer_is_composed_from_claims_only():
    d = template.render(_facts())
    assert d.answer == template.compose(d.claims)
    assert "[cit-1][cit-2][cit-3]" in d.answer


def test_intent_dataclass_mentions_default():
    assert Intent("q", Scope(), None).mentions == []
