"""Prepare all five source PDFs offline; keep extraction quality and scope explicit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from app.core.config import REPO_ROOT

MAJORS = ("计算机科学与技术", "网络工程", "数据科学与大数据技术", "软件工程")
COLLEGE = "计算机学院（国家示范性软件学院）"


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def _heading(text: str) -> dict | None:
    top = "".join(text.split())[:350]
    # TOCs contain dotted page references and do not contain the programme body opening.
    if "一、专业定位" not in top and "一、培养目标" not in top:
        return None
    start = top.split("一、", 1)[0]
    if "目录" in top[:12] or re.search(r"\.{5,}|…{2,}", start):
        return None
    if "培养方案" not in start:
        return None
    major = next((name for name in MAJORS if name in start), None)
    if major is None:
        return None
    variant = (
        "international"
        if "留学生" in start
        else "second_degree"
        if "第二学士" in start
        else "joint"
        if "会计学" in start
        else "regular"
    )
    revision = re.search(r"(20\d{2})年版", start)
    return {
        "major": major,
        "program_variant": variant,
        "program_title": start,
        "printed_revision": revision[1] if revision else None,
    }


def _windows(text: str, limit: int = 1800) -> list[str]:
    """Use line boundaries; preserve source text and do not reconstruct table cells."""
    lines = text.splitlines(keepends=True)
    result, current, size = [], [], 0
    for line in lines:
        if current and size + len(line) > limit:
            result.append("".join(current).strip())
            current = current[-2:]
            size = sum(map(len, current))
        current.append(line)
        size += len(line)
    if current and "".join(current).strip():
        result.append("".join(current).strip())
    return [r for r in result if r]


def prepare(root: Path, output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory; never overwrite prepared source data")
    documents, chunks, inventory = [], [], []
    correction_file = root / "data/processed/ocr/rules_corrections.json"
    corrections = (
        json.loads(correction_file.read_text(encoding="utf-8")) if correction_file.exists() else []
    )
    corrections = {(c["source_file"], c["page"]): c for c in corrections}
    for source in sorted((root / "data/raw").glob("*.pdf")):
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        year_match = re.search(r"(202[345])级", source.name)
        year = int(year_match[1]) if year_match else None
        doc_id = (
            f"curriculum-{year}"
            if year
            else "assessment-rules"
            if "课程考核" in source.name
            else "degree-rules"
        )
        if year:
            pages = read_jsonl(root / f"data/processed/native/curriculum_{year}.jsonl")
            supplement = root / f"data/processed/ocr/curriculum_{year}_supplement.jsonl"
            replacements = (
                {p["page"]: p for p in read_jsonl(supplement)} if supplement.exists() else {}
            )
            pages = [replacements.get(p["page"], p) for p in pages]
        else:
            name = "assessment_rules_2022" if doc_id == "assessment-rules" else "degree_rules_2025"
            pages = read_jsonl(root / f"data/processed/ocr/{name}.jsonl")
        if any(p["source_sha256"] != sha for p in pages):
            raise ValueError("Source extraction is stale: " + source.name)
        if [p["page"] for p in pages] != list(range(1, len(pages) + 1)):
            raise ValueError("Incomplete source page coverage: " + source.name)
        for p in pages:
            c = corrections.get((source.name, p["page"]))
            if c:
                if (
                    c["source_sha256"] != sha
                    or c["text_sha256"] != hashlib.sha256(p["text"].encode()).hexdigest()
                ):
                    raise ValueError("OCR correction does not match its original source")
                p["text"] = c["text"]
                p["reviewed"] = c["reviewed"]
                p["review_notes"] = c["notes"]
        document = {
            "doc_id": doc_id,
            "doc_version": "source-" + sha[:12],
            "title": source.stem,
            "source_file": source.name,
            "source_uri": "data/raw/" + source.name,
            "source_sha256": sha,
            "book_year": year,
            "pages": len(pages),
        }
        documents.append(document)
        program = None
        section = None
        section_inventory = []
        for p in pages:
            native = p["text"]
            is_toc = bool(re.search(r"\.{5,}|…{2,}", native))
            candidate = _heading(native) if year else None
            if candidate:
                program = candidate
                section_inventory.append({"page": p["page"], **candidate})
            if year and re.search(r"^\s*(?:附录|附件)\s*\d+[：:]", native, re.M):
                program = None
            heading = re.search(
                r"^\s*(?:第[一二三四五六七八九十百]+[条章]|[一二三四五六七八九十]+、)[^\n]{0,65}",
                native,
                re.M,
            )
            if heading:
                section = heading[0].strip()
            for position, text in enumerate(_windows(native)):
                content_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
                chunk_id = (
                    "doc-"
                    + hashlib.sha256(
                        f"{sha}|{p['page']}|{position}|{content_sha}".encode()
                    ).hexdigest()[:24]
                )
                ocr = bool(p.get("ocr"))
                reviewed = bool(p.get("reviewed"))
                # The older 2021 revision inside the 2023 book is not silently relabelled 2023.
                printed = program.get("printed_revision") if program else None
                entry_year = year if not printed or printed == str(year) else None
                chunks.append(
                    {
                        **document,
                        "chunk_id": chunk_id,
                        "page_start": p["page"],
                        "page_end": p["page"],
                        "section": section,
                        "text": text,
                        "text_sha256": content_sha,
                        "kind": "curriculum" if year else "institution",
                        "college": COLLEGE if year else None,
                        "entry_year": entry_year,
                        "major": program.get("major") if program else None,
                        "program_variant": program.get("program_variant") if program else None,
                        "plan_revision": printed or str(year) if year else None,
                        "program_title": program.get("program_title") if program else None,
                        "source_kind": "ocr" if ocr else "native_text",
                        "needs_review": ocr and not reviewed,
                        "verification_status": "ai_source_reviewed"
                        if reviewed
                        else "ocr_unreviewed"
                        if ocr
                        else "source_text_extracted",
                        "verified_by": "codex-ai-ocr-source-review" if reviewed else None,
                        "scope_note": "Source excerpt, not confirmation of applicability to a cohort",
                        "is_toc": is_toc,
                    }
                )
        inventory.append(
            {
                **document,
                "programs": section_inventory,
                "ocr_pages": [p["page"] for p in pages if p.get("ocr")],
                "empty_pages": [p["page"] for p in pages if not p["text"].strip()],
            }
        )
    if len(documents) != 5:
        raise ValueError("Expected the five agreed PDFs")
    output.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks)
    (output / "chunks.jsonl").write_bytes(data.encode("utf-8"))
    manifest = hashlib.sha256(data.encode()).hexdigest()
    report = {
        "documents": documents,
        "inventory": inventory,
        "page_count": sum(d["pages"] for d in documents),
        "chunk_count": len(chunks),
        "chunks_sha256": manifest,
        "boundary": "Full source-text coverage; no claim that all extracted/OCR text is verified",
        "ocr_chunk_count": sum(c["needs_review"] for c in chunks),
    }
    (output / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "data/corpus/all-documents-v3")
    args = parser.parse_args()
    report = prepare(REPO_ROOT, args.output)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("page_count", "chunk_count", "ocr_chunk_count", "chunks_sha256")
            }
        )
    )
