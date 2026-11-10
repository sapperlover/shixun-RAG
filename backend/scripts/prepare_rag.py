"""Offline real-source candidate bundle. Never approves relations or publishes.

Run from backend: python -m scripts.prepare_rag --output ../data/kb/cs2024
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from app.core.config import REPO_ROOT
from app.ingest import bundle, chunk, extract_rules, parse, verify_csv
from app.ingest.normalize import normalize_surface
from app.ingest.review import REVIEW_MARKER

MAJOR = "计算机科学与技术"
COLLEGE = "计算机学院（国家示范性软件学院）"
PLAN_DOC = "bupt-cs-plan-2024"
PLAN_ID = f"plan:{MAJOR}:2024:source"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select_program(pages: list[tuple[int, str]], title: str) -> list[tuple[int, str]]:
    """Exclude TOC and similarly named overseas/second-degree programmes."""
    start = None
    end = len(pages)
    heading = re.compile(r"^\s*[^\n。]{2,60}(?:专业培养方案|学位培养方案)\s*$", re.M)
    for index, (_, text) in enumerate(pages):
        names = [normalize_surface(m.group()) for m in heading.finditer(text)]
        if start is None and normalize_surface(title) in names:
            if "一、专业定位" in normalize_surface(text):
                start = index
        elif start is not None and names:
            end = index
            break
    if start is None:
        raise ValueError(f"Cannot locate exact programme body: {title}")
    return pages[start:end]


def _write_csv(path: Path, columns: list[str], rows: list[dict]):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def select_innovation_appendix(all_pages: list[tuple[int, str]], after_page: int):
    """Require a full body heading, excluding the TOC's dotted page references."""
    starts = [
        i
        for i, (page, text) in enumerate(all_pages)
        if page > after_page
        and re.search(r"^\s*附录\s*4[：:]\s*创新实践学分及成绩认定方案\s*$", text, re.M)
    ]
    if len(starts) != 1:
        raise ValueError("Expected exactly one appendix 4 body, not its table-of-contents entry")
    return all_pages[starts[0] :]


def _write_jsonl(path: Path, rows: list[dict]):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def prepare(output: Path, raw: Path, ocr: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output is not empty; preserve reviewed work: {output}")
    plan_files = sorted(raw.glob("*2024*.pdf"))
    if len(plan_files) != 1:
        raise ValueError("Expected exactly one 2024 source PDF")
    plan_path = plan_files[0]
    all_pages = parse.parse(plan_path)
    pages = select_program(all_pages, f"{MAJOR}专业培养方案")
    # Only resolve the reference whose number AND subject agree with the source.
    # The source has other appendix-number/title inconsistencies; do not guess.
    appendix_pages = []
    referring_text = normalize_surface("\n".join(t for _, t in pages))
    if re.search(r"创新实践.{0,80}详见附录4", referring_text):
        appendix_pages = select_innovation_appendix(all_pages, pages[-1][0])
    chunks = chunk.split(PLAN_DOC, "2024-source", pages + appendix_pages)
    documents = []
    processed = [
        {"doc_id": PLAN_DOC, "page": p, "text": t, "ocr": False} for p, t in pages + appendix_pages
    ]

    def document(path, doc_id, version, title, scoped):
        return dict(
            zip(
                bundle.DOCUMENT_COLUMNS,
                [
                    doc_id,
                    version,
                    title,
                    path.resolve().as_uri(),
                    "用户确认：学校公开发布、用于本次课程项目；原始下载链接待补充",
                    "public",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    COLLEGE if scoped else "",
                    MAJOR if scoped else "",
                    "2024" if scoped else "",
                    REVIEW_MARKER
                    + "; source_version_label_only; verify scope and OCR before publication",
                ],
                strict=True,
            )
        )

    documents.append(document(plan_path, PLAN_DOC, "2024-source", plan_path.stem, True))
    for name, doc_id in [
        ("assessment_rules_2022", "bupt-assessment-source"),
        ("degree_rules_2025", "bupt-degree-source"),
    ]:
        lines = (ocr / (name + ".jsonl")).read_text(encoding="utf-8-sig").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
        if not rows or [r["page"] for r in rows] != list(range(1, len(rows) + 1)):
            raise ValueError(f"Incomplete OCR pages: {name}")
        source = raw / rows[0]["source_file"]
        file_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        if any(r["source_sha256"].lower() != file_sha for r in rows):
            raise ValueError(f"Stale OCR does not match PDF: {name}")
        version = "source-" + file_sha[:12]
        documents.append(document(source, doc_id, version, source.stem, False))
        chunks.extend(chunk.split(doc_id, version, [(r["page"], r["text"]) for r in rows]))
        processed.extend({"doc_id": doc_id, **r} for r in rows)

    entities: dict[str, dict] = {}
    relations: dict[tuple, dict] = {}
    by_chunk = {c.chunk_id: c for c in chunks}

    def entity(eid, label, name, props, aliases=None):
        entities.setdefault(
            eid, dict(entity_id=eid, label=label, name=name, aliases=aliases or [], props=props)
        )

    def relation(kind, a, b, source, note):
        key = (kind, a, b)
        if key in relations:
            row = relations[key]
            evidence_ids = set(bundle.split_ids(row["evidence_chunk_ids"]))
            evidence_ids.add(source.chunk_id)
            row["evidence_chunk_ids"] = ";".join(sorted(evidence_ids))
            return
        relations[key] = dict(
            zip(
                verify_csv.COLUMNS,
                [
                    kind,
                    a,
                    entities[a]["label"],
                    b,
                    entities[b]["label"],
                    MAJOR,
                    "2024",
                    source.chunk_id,
                    source.text[:1000],
                    "",
                    "rule_candidate",
                    "unverified",
                    "",
                    "",
                    note,
                ],
                strict=True,
            )
        )

    entity(f"major:{MAJOR}", "Professional", MAJOR, {"major_code": MAJOR, "college_code": COLLEGE})
    entity(
        PLAN_ID,
        "ProgramPlan",
        "计算机科学与技术2024级培养方案",
        {"major_id": f"major:{MAJOR}", "entry_year": 2024, "plan_revision": "source"},
        ["计算机科学与技术专业培养方案"],
    )
    relation("APPLIES_TO", PLAN_ID, f"major:{MAJOR}", chunks[0], "专业与年级必须对照原PDF确认")
    plan_chunks = [c for c in chunks if c.doc_id == PLAN_DOC]
    observations = extract_rules.extract(plan_chunks)
    for observation in observations:
        source = by_chunk[observation["chunk_id"]]
        if observation["kind"] == "course":
            entity(
                "course:" + observation["code"],
                "Course",
                observation["name"],
                {"course_code": observation["code"]},
            )
            continue
        name = observation["name"]
        category_id = f"category:{PLAN_ID}:{_sha(name)[:10]}"
        entity(
            category_id,
            "CourseCategory",
            name,
            {"plan_id": PLAN_ID, "category_code": _sha(name)[:10]},
        )
        # The course-setting section is the only category-membership source;
        # mentions in graduation matrices alone do not imply membership.
        is_program_section = bool(source.section) and (
            "课程设置" in source.section or source.section.startswith("十三、创新实践")
        )
        if is_program_section:
            relation("CONTAINS", PLAN_ID, category_id, source, "核对方案确实包含此课程类别")
        if observation["kind"] == "category_rule_candidate" and is_program_section:
            rule_id = (
                f"rule:{source.doc_id}:{source.doc_version}:{source.chunk_id}:{_sha(name)[:10]}"
            )
            entity(
                rule_id,
                "RuleClause",
                f"{name}要求（{source.section}）",
                {
                    "doc_id": source.doc_id,
                    "doc_version": source.doc_version,
                    "section": source.section,
                },
            )
            relation(
                "CITES",
                category_id,
                rule_id,
                source,
                "待核验：类别与本块规范性条款是否直接对应；仅同页出现不构成确认",
            )

    if appendix_pages:
        category_id = f"category:{PLAN_ID}:{_sha('创新实践')[:10]}"
        referring = next(c for c in plan_chunks if c.section and "十三、创新实践" in c.section)
        appendix = next(
            c for c in plan_chunks if c.section and "附录" in c.section and "创新实践" in c.section
        )
        rule_id = f"rule:{appendix.doc_id}:{appendix.doc_version}:{appendix.chunk_id}"
        entity(
            rule_id,
            "RuleClause",
            "创新实践学分及成绩认定方案",
            {
                "doc_id": appendix.doc_id,
                "doc_version": appendix.doc_version,
                "section": appendix.section,
            },
        )
        relation(
            "CITES", category_id, rule_id, referring, "原方案明确引用附录4；仍需人工复核适用范围"
        )
        relation("CITES", category_id, rule_id, appendix, "附录4完整表格与条款来源")

    # OCR clauses are searchable source entities, but not connected to the 2024
    # programme without a human-reviewed applicability/reference statement.
    for c in chunks:
        if c.doc_id != PLAN_DOC and c.section:
            entity(
                f"rule:{c.doc_id}:{c.doc_version}:{c.chunk_id}",
                "RuleClause",
                c.section,
                {"doc_id": c.doc_id, "doc_version": c.doc_version, "section": c.section},
            )

    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "documents.csv", bundle.DOCUMENT_COLUMNS, documents)
    _write_jsonl(output / "chunks.jsonl", [asdict(c) for c in chunks])
    _write_jsonl(output / "entities.jsonl", list(entities.values()))
    _write_csv(output / "relations.csv", verify_csv.COLUMNS, list(relations.values()))
    _write_jsonl(output / "source_pages.jsonl", processed)
    checklist = [
        {
            "doc_id": c.doc_id,
            "chunk_id": c.chunk_id,
            "section": c.section,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "content_reviewed": "no",
            "scope_reviewed": "no",
            "review_note": "",
        }
        for c in chunks
    ]
    _write_csv(output / "review_checklist.csv", list(checklist[0]), checklist)
    # Proposed gold paths only: invalid for the formal evaluator until the user
    # reviews both the relation mapping and each question independently.
    question_candidates = []
    applies = next(r for r in relations.values() if r["type"] == "APPLIES_TO")
    by_category = {r["to_entity_id"]: r for r in relations.values() if r["type"] == "CONTAINS"}
    cites = [
        r for r in relations.values() if r["type"] == "CITES" and r["from_entity_id"] in by_category
    ]
    for hops in (2, 3):
        for i, citation in enumerate(cites[:5], 1):
            cat_id = citation["from_entity_id"]
            name = entities[cat_id]["name"]
            chain = [by_category[cat_id], citation]
            if hops == 3:
                chain.insert(0, applies)
            prefix = "2024级培养方案中" if hops == 2 else "计算机科学与技术专业2024级的"
            source_ids = sorted(
                {cid for r in chain for cid in bundle.split_ids(r["evidence_chunk_ids"])}
            )
            question_candidates.append(
                dict(
                    question_id=f"cs2024-t{hops - 1}-{i:03d}",
                    question=f"{prefix}{name}有哪些修读要求？",
                    scope={"major_code": MAJOR, "entry_year": 2024},
                    expected_status="success",
                    gold_relation_path=[
                        {"from": r["from_entity_id"], "type": r["type"], "to": r["to_entity_id"]}
                        for r in chain
                    ],
                    source_evidence_ids=source_ids,
                    hop_count=hops,
                    doc_version="2024-source",
                    review_status="unverified",
                    reviewed_by="",
                )
            )
    _write_jsonl(output / "evaluation_candidates.jsonl", question_candidates)
    result = bundle.load(output)
    report = dict(
        state="awaiting_human_review",
        documents=len(documents),
        chunks=len(chunks),
        entities=len(entities),
        relations=len(relations),
        verified_relations=0,
        selected_program_pdf_pages=[pages[0][0], pages[-1][0]],
        included_shared_appendix_pdf_pages=[p for p, _ in appendix_pages],
        manifest_sha256=result.manifest_sha,
        candidate_questions=len(question_candidates),
        evaluation="not_frozen; no verified gold paths yet",
        warnings=[
            "Course-map page may be image-only; no prerequisites inferred",
            "OCR numbers/formulas/tables require visual review",
            "No applicability edges inferred for the two institution-wide rules",
            "Appendix references require review; not automatically resolved",
        ],
    )
    (output / "preparation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--raw", type=Path, default=REPO_ROOT / "data/raw")
    ap.add_argument("--ocr", type=Path, default=REPO_ROOT / "data/processed/ocr")
    args = ap.parse_args()
    print(json.dumps(prepare(args.output, args.raw, args.ocr), ensure_ascii=False, indent=2))
