"""评测报告导出（Markdown）：指标、失败分布、逐题结果、运行环境。

TODO(QA, D5)：补充资源占用（峰值 RSS/VRAM）与时延 P50/P95（V1.2 附录 D.4）。
"""

from __future__ import annotations

import json
from pathlib import Path


def to_markdown(run_dir: Path) -> str:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    m = summary["metrics"]

    def pct(x):
        return "N/A" if x is None else f"{x:.1%}"

    lines = [
        f"# 评测报告 {summary['run_id']}",
        "",
        f"- git commit：{summary['git_commit']}；评分脚本版本：{summary['scorer_version']}",
        f"- 题数：{m['questions']}",
        f"- 路径命中率：{pct(m['path_hit_rate'])}",
        f"- 答案正确率：{pct(m['answer_accuracy'])}（自动初判，需人工复核）",
        f"- 引用覆盖率：{pct(m['citation_coverage'])}",
        "",
        "## 失败分布",
        *[f"- {k}: {v}" for k, v in m["failure_distribution"].items()],
    ]
    return "\n".join(lines) + "\n"
