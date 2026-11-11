"""运行并持久化正式评测；可用 --no-freeze-check 单独运行调试题集。"""

import argparse
from pathlib import Path

from dotenv import load_dotenv

from app.core.config import REPO_ROOT, get_env, get_settings
from app.eval import dataset, report, runner, service
from app.storage import sqlite

if __name__ == "__main__":
    load_dotenv(REPO_ROOT / ".env")
    get_env.cache_clear()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dataset", nargs="?")
    ap.add_argument("--no-freeze-check", action="store_true", help="调试题集不写入正式评测列表")
    args = ap.parse_args()

    out_dir = REPO_ROOT / get_settings().eval.runs_dir
    if args.no_freeze_check:
        if not args.dataset:
            ap.error("调试模式需要指定题集文件")
        run_id, _ = runner.run(dataset.load(Path(args.dataset)), out_dir)
    else:
        if args.dataset:
            ap.error("正式评测统一使用 config/settings.yaml 中的冻结题集")
        sqlite.migrate()
        sha, _ = service.frozen_dataset()
        run_id = service.create_run(sha)
        service.execute(run_id)
        with sqlite.connect() as conn:
            row = conn.execute(
                "SELECT status,error_detail FROM eval_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if row["status"] != "finished":
            raise SystemExit(row["error_detail"])
    markdown = report.to_markdown(out_dir / run_id)
    (out_dir / run_id / "report.md").write_text(markdown, encoding="utf-8")
    print(markdown)
