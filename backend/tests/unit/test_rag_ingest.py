import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.ingest import bundle, chunk, parse, review
from scripts.prepare_rag import select_innovation_appendix, select_program


def test_appendix_excludes_toc_and_other_programmes():
    pages = [
        (4, "附录 4：创新实践学分及成绩认定方案 ........ 131"),
        (27, "网络工程专业培养方案"),
        (135, "附录 4：创新实践学分及成绩认定方案\n正文"),
        (136, "续表"),
    ]
    assert [p for p, _ in select_innovation_appendix(pages, 26)] == [135, 136]


def test_same_source_table_has_category_specific_rule_names(tmp_path, monkeypatch):
    from scripts import prepare_rag
    from scripts.review_rag_bundle import render

    raw, ocr = tmp_path / "raw", tmp_path / "ocr"
    raw.mkdir()
    ocr.mkdir()
    (raw / "plan2024.pdf").write_bytes(b"test-plan")
    monkeypatch.setattr(
        prepare_rag.parse,
        "parse",
        lambda path: [
            (
                5,
                "计算机科学与技术专业培养方案\n一、专业定位\n正文\n十二、课程设置\n通识教育课程\n合计必修1学分\n专业教育课程\n合计必修2学分",
            ),
            (27, "网络工程专业培养方案\n一、专业定位"),
        ],
    )
    for name in ("assessment_rules_2022", "degree_rules_2025"):
        source = raw / (name + ".pdf")
        source.write_bytes(name.encode())
        row = {
            "page": 1,
            "text": "第一条正文",
            "source_file": source.name,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
        (ocr / (name + ".jsonl")).write_text(json.dumps(row), encoding="utf-8")
    root = tmp_path / "prepared"
    prepare_rag.prepare(root, raw, ocr)
    b = bundle.load(root)
    entities = {e.entity_id: e for e in b.entities}
    citations = [r for r in b.relations if r["type"] == "CITES"]
    assert len(citations) == 2
    assert len({r["to_entity_id"] for r in citations}) == 2
    for r in citations:
        assert entities[r["to_entity_id"]].name.startswith(entities[r["from_entity_id"]].name)
    before = b.manifest_sha
    report = render(root)
    assert "待核验" in report and "专业教育课程要求" in report
    assert bundle.load(root).manifest_sha == before


def test_exact_program_isolation():
    pages = [
        (1, "目录\n计算机科学与技术专业培养方案 ........1"),
        (5, "计算机科学与技术专业培养方案\n一、专业定位\n正文"),
        (6, "课程设置"),
        (7, "网络工程专业培养方案\n一、专业定位"),
    ]
    assert [p for p, _ in select_program(pages, "计算机科学与技术专业培养方案")] == [5, 6]


def test_continued_table_preserves_pages_and_clause_boundaries():
    pages = [
        (3, "十二、课程设置\n课程编号  课程名称 学分\n1234567890  数据结构  4"),
        (4, "课程编号  课程名称 学分\n1234567891  操作系统  4\n十三、创新实践\n4学分"),
    ]
    rows = chunk.split("d", "v", pages)
    assert len(rows) == 2
    assert rows[0].page_start == 3 and rows[0].page_end == 4
    assert "数据结构" in rows[0].text and "操作系统" in rows[0].text
    assert rows[0].section == "十二、课程设置"
    clauses = chunk.split(
        "r", "v", [(1, "第一章总则\n第一条正文\n第二条适用范围"), (2, "延续内容\n第三条新条款")]
    )
    assert [c.section for c in clauses] == ["第一章总则", "第一条", "第二条", "第三条"]
    assert clauses[2].page_end == 2


def test_deduplicates_same_content_with_stable_id():
    a = chunk.split("d", "v", [(1, "第一条正文"), (2, "第一条正文")])
    b = chunk.split("d", "v", [(1, "第一条正文")])
    assert len(a) == 1 and a[0].chunk_id == b[0].chunk_id


def test_parser_pdf_docx_txt_and_scanned_pdf(tmp_path):
    from docx import Document
    from pypdf import PdfWriter

    text = tmp_path / "test.txt"
    text.write_text("原文", encoding="utf-8")
    assert parse.parse(text) == [(0, "原文")]
    doc = Document()
    doc.add_paragraph("正文")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "课程"
    table.cell(0, 1).text = "学分"
    doc.add_paragraph("后文")
    doc.save(tmp_path / "test.docx")
    extracted = parse.parse(tmp_path / "test.docx")[0][1]
    assert extracted.index("正文") < extracted.index("课程 | 学分") < extracted.index("后文")
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(tmp_path / "scan.pdf")
    with pytest.raises(ValueError, match="offline OCR"):
        parse.parse(tmp_path / "scan.pdf")
    with pytest.raises(ValueError, match="extension"):
        parse.parse(tmp_path / "fake.exe")


def test_human_gate_rejects_unreviewed_and_stale_bundles(tmp_path):
    demo = Path(__file__).parents[3] / "data/demo"
    shutil.copytree(demo, tmp_path / "kb")
    root = tmp_path / "kb"
    b = bundle.load(root)
    review.check(b)  # unchanged demo contract
    b.documents[0]["notes"] = review.REVIEW_MARKER
    with pytest.raises(bundle.BundleError, match="unreviewed"):
        review.check(b)
    for relation in b.relations:
        if relation["verification_status"] == "unverified":
            relation["verification_status"] = "rejected"
    with pytest.raises(bundle.BundleError, match="Missing human approval"):
        review.check(b)
    approval = dict(
        reviewer="user",
        reviewed_at="2026-11-09T00:00:00Z",
        source_content_reviewed=True,
        scope_reviewed=True,
        manifest_sha256=b.manifest_sha,
    )
    (root / "review_approval.json").write_text(json.dumps(approval), encoding="utf-8")
    review.check(b)
    b.manifest_sha = hashlib.sha256(b"changed").hexdigest()
    with pytest.raises(bundle.BundleError, match="changed after review"):
        review.check(b)


def test_delegated_ai_review_is_distinct_from_human_review(tmp_path):
    demo = Path(__file__).parents[3] / "data/demo"
    shutil.copytree(demo, tmp_path / "kb")
    root = tmp_path / "kb"
    b = bundle.load(root)
    b.documents[0]["notes"] = review.SOURCE_REVIEW_MARKER
    for relation in b.relations:
        if relation["verification_status"] == "unverified":
            relation["verification_status"] = "rejected"
    decisions = b'{"review_kind":"ai_source_review"}'
    (root / "review_decisions.json").write_bytes(decisions)
    approval = dict(
        reviewer="codex-ai-source-review", reviewed_at="2026-11-09T00:00:00Z",
        source_content_reviewed=True, scope_reviewed=True, manifest_sha256=b.manifest_sha,
        review_kind="ai_source_review", delegated_by="user", delegation_note="那你直接确认",
        decision_report_sha256=hashlib.sha256(decisions).hexdigest(),
    )

    def save():
        (root / "review_approval.json").write_text(json.dumps(approval), encoding="utf-8")

    save()
    review.check(b)
    approval["delegated_by"] = None
    save()
    with pytest.raises(bundle.BundleError, match="explicit delegation"):
        review.check(b)
    approval["delegated_by"] = "user"
    save()
    b.documents[0]["notes"] = review.REVIEW_MARKER
    with pytest.raises(bundle.BundleError, match="source-review marker"):
        review.check(b)
    b.documents[0]["notes"] = review.SOURCE_REVIEW_MARKER
    (root / "review_decisions.json").write_bytes(b"changed")
    with pytest.raises(bundle.BundleError, match="decisions changed"):
        review.check(b)


def test_source_reviewed_real_bundle_and_development_questions():
    from app.eval import retrieval

    root = Path(__file__).parents[3] / "data/kb/cs2024-reviewed"
    b = bundle.load(root)
    review.check(b)
    assert len(b.documents) == 1
    assert sum(r["verification_status"] == "verified" for r in b.relations) == 15
    assert sum(r["verification_status"] == "rejected" for r in b.relations) == 1
    assert not any(r["verification_status"] == "unverified" for r in b.relations)
    path = root / "retrieval_questions.jsonl"
    questions = retrieval.load(path, (root / "retrieval_questions.sha256").read_text().strip())
    assert len(questions) == 10
    assert sum(q.hop_count == 2 for q in questions) == 5
    assert sum(q.hop_count == 3 for q in questions) == 5
    assert all(q.reviewed_by == "codex-ai-source-review" for q in questions)
    verified = {(r["from_entity_id"], r["type"], r["to_entity_id"])
                for r in b.relations if r["verification_status"] == "verified"}
    for q in questions:
        assert all((e.from_, e.type, e.to) in verified for e in q.gold_relation_path)
