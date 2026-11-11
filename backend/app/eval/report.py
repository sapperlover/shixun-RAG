"""可复核的 Markdown 报告：指标、逐题路径、来源、回答和失败归因。"""

from __future__ import annotations

import json
from pathlib import Path


def to_markdown(run_dir: Path) -> str:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    records = [
        json.loads(s) for s in (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    m = summary["metrics"]

    def pct(x):
        return "N/A" if x is None else f"{x:.1%}"

    def ms(key):
        return "N/A" if m.get(key) is None else f"{m[key]:.0f} ms"

    lines = [
        f"# 评测报告 {summary['run_id']}",
        "",
        "题集为依据真实原文编制的开发验证集；答案评分为要点自动初判，需人工逐题复核。",
        "负例参与终态正确率，路径命中率只统计正例；摘录降级不会计为 API 生成成功。",
        "",
        f"- git commit：{summary['git_commit']}；评分脚本版本：{summary['scorer_version']}",
        f"- 题数（含负例）：{m['questions']}",
        f"- 路径命中率：{pct(m['path_hit_rate'])}",
        f"- 2 跳路径命中率：{pct(m.get('two_hop_path_hit_rate'))}",
        f"- 3 跳路径命中率：{pct(m.get('three_hop_path_hit_rate'))}",
        f"- 答案要点命中率：{pct(m['answer_accuracy'])}",
        f"- 引用覆盖率：{pct(m['citation_coverage'])}",
        f"- API 生成占比（正例）：{pct(m.get('api_answer_rate'))}",
        f"- 平均 / P95 耗时：{ms('average_latency_ms')} / {ms('p95_latency_ms')}",
        "",
        "## 失败分布",
        "",
        *(
            [f"- {k}：{v}" for k, v in m["failure_distribution"].items()]
            or ["自动评分未发现失败项。"]
        ),
        "",
        "## 逐题结果",
        "",
    ]
    for r in records:
        response = r.get("response") or {}
        lines += [
            f"### {r['question_id']} · {r.get('hop_count') or '边界'}跳",
            "",
            r.get("question", ""),
            "",
            f"- 预期 / 实际状态：{r.get('expected_status')} / {r['status']}",
            f"- 路径：{'命中' if r['path_hit'] else '未命中'}；"
            f"答案：{'通过自动初判' if r['answer_correct'] else '需复核'}",
            f"- 生成方式：{r.get('answer_mode') or '无'}；耗时：{r['elapsed_ms']} ms",
            f"- 失败归因：{r.get('failure_stage') or '无'}；批次：{r.get('batch_id')}",
            "",
            r.get("answer") or "未生成结论。",
            "",
        ]
        for path in response.get("paths", []):
            lines.append(f"路径 `{path['path_id']}`：")
            lines += [f"- `{e['from']}` — {e['type']} → `{e['to']}`" for e in path["edges"]]
            lines.append("")
        for citation in response.get("citations", []):
            lines += [
                f"- 来源 `{citation['citation_id']}`：{citation.get('doc_title') or citation['doc_id']} "
                f"{citation['doc_version']}，PDF 第 {citation.get('page') or '?'} 页",
                "",
                "> " + citation["excerpt"].replace("\n", "\n> "),
                "",
            ]
        if response.get("degradation_reason"):
            lines += [f"降级原因：{response['degradation_reason']}", ""]
    lines += [
        "## 算法配置",
        "",
        "```json",
        json.dumps(summary["settings"], ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)
