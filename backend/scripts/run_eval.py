"""运行评测：python -m scripts.run_eval [题集.jsonl] [--no-freeze-check]

默认读取 settings.yaml 中的冻结题集，并校验其 sha256 与 .sha256 文件一致。
"""

import argparse
from pathlib import Path

from app.core.config import REPO_ROOT, get_settings
from app.eval import dataset, report, runner

if __name__ == "__main__":
    cfg = get_settings().eval
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", nargs="?", default=str(REPO_ROOT / cfg.dataset_file))
    ap.add_argument("--no-freeze-check", action="store_true", help="调试用，正式评测不得使用")
    args = ap.parse_args()

    expected = None
    if not args.no_freeze_check:
        sha_file = REPO_ROOT / cfg.dataset_sha256_file
        expected = sha_file.read_text().split()[0] if sha_file.exists() else None
        if expected is None:
            raise SystemExit(f"未找到冻结哈希 {sha_file}；D1 冻结题集后执行 sha256sum 生成")

    qs = dataset.load(Path(args.dataset), expected)
    out_dir = REPO_ROOT / cfg.runs_dir
    run_id, m = runner.run(qs, out_dir)
    print(report.to_markdown(out_dir / run_id))
