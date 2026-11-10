"""Render a read-only review packet; never approve or rewrite bundle evidence."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from app.ingest import bundle


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render(root: Path) -> str:
    b = bundle.load(root)
    entities = {e.entity_id: e for e in b.entities}
    chunks = {c["chunk_id"]: c for c in b.chunks}
    documents = {d["doc_id"]: d for d in b.documents}
    lines = [
        "# 真实知识包核验材料",
        "",
        f"知识包：`{root.name}`；四文件哈希：`{b.manifest_sha}`。",
        "",
        "此材料由程序整理，不代表已完成内容核验。只读生成，不修改任何确认状态。",
        "",
        "## 当前状态",
        "",
        f"文档 {len(b.documents)} 份，文本块 {len(b.chunks)} 个，关系 {len(b.relations)} 条。",
        f"关系状态：`{dict(Counter(r['verification_status'] for r in b.relations))}`。",
        "",
        "先看下表，再逐条对照原PDF。页码均为PDF物理页，不是印刷页码。",
        "同一完整表格可能为多个类别提供证据，不能仅凭同页出现就确认 CITES。",
        "",
        "| 序号 | 关系 | 起点 | 终点 | 状态 |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(b.relations, 1):
        a, z = entities[r["from_entity_id"]], entities[r["to_entity_id"]]
        lines.append(
            f"| {i} | {r['type']} | {_cell(a.name)} | {_cell(z.name)} | {r['verification_status']} |"
        )
    for i, r in enumerate(b.relations, 1):
        a, z = entities[r["from_entity_id"]], entities[r["to_entity_id"]]
        lines.extend(
            [
                "",
                f"## 关系 {i}：{a.name} → {z.name}",
                "",
                f"类型：`{r['type']}`；当前状态：`{r['verification_status']}`。",
                "",
                f"核对重点：{r['note']}",
                "",
            ]
        )
        for cid in bundle.split_ids(r["evidence_chunk_ids"]):
            c = chunks[cid]
            d = documents[c["doc_id"]]
            lines.extend(
                [
                    f"来源：{d['title']}，PDF第 {c.get('page_start')}–{c.get('page_end')} 页，"
                    f"{c.get('section') or '标题/正文'}。",
                    "",
                    f"文本块：`{cid}`；版本：`{c['doc_version']}`。",
                    "",
                ]
            )
            # Display local source lines verbatim, not an LLM summary or reconstructed number.
            source_lines = c["text"].splitlines()
            needle = re.sub(r"\s+", "", a.name)
            hits = [j for j, line in enumerate(source_lines) if needle in re.sub(r"\s+", "", line)]
            wanted = set()
            for j in hits[:3] or [0]:
                wanted.update(range(max(0, j - 1), min(len(source_lines), j + 5)))
            lines.append("原文定位摘录（非完整条款，确认时须看完整文本块和PDF）：")
            lines.append("")
            lines.extend("> " + source_lines[j] for j in sorted(wanted))
            lines.append("")
    questions_file = root / "evaluation_candidates.jsonl"
    if questions_file.exists():
        lines.extend(
            [
                "## 候选题核验",
                "",
                "以下均为待核验题，不是冻结金标准。应分别确认题意、完整路径、引用和版本；",
                "不能用把期望状态改成 success 的方式代替核验。",
                "",
            ]
        )
        for line in questions_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            q = json.loads(line)
            lines.append(
                f"- `{q['question_id']}`（{q['hop_count']}跳，{q['review_status']}）：{q['question']}"
            )
    lines.extend(
        [
            "",
            "## 如何记录核验结果",
            "",
            "在 review_checklist.csv 核对文本与范围，在 relations.csv 记录 verified/rejected 和真实核验人、时间。",
            "本报告不写入签核，原知识包与此报告哈希不一致时应重新生成。",
            "扫描件中的数字、否定词、公式和表格须核对原页；两份制度与2024级方案的适用关系尚未建立。",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        ap.error("Refusing to overwrite review notes; choose a new output path")
    report = render(args.bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
