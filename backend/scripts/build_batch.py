"""构建 → 校验 → 发布一个知识批次（V1.2 附录 B.2）。

用法：python -m scripts.build_batch <知识包目录> [--questions 题集.jsonl] [--publish]
  不带 --publish 时只构建和校验（state=validated），不影响线上 active 批次。
"""

import argparse
import json
import sys

from app.graph import build, publish, validate
from app.ingest.bundle import BundleError
from app.storage import neo4j_client

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--questions", help="冻结题集；校验金标准路径在本批次中连通")
    ap.add_argument("--publish", action="store_true", help="校验通过后切换为 active")
    args = ap.parse_args()

    try:
        batch = build.build_staging(args.bundle)
    except BundleError as exc:
        sys.exit(str(exc))
    print(f"已构建 staging 批次 {batch}")

    report = validate.validate(batch, args.questions)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        sys.exit(f"批次 {batch} 校验失败，已标记 failed")

    if args.publish:
        old = publish.publish(batch)
        print(f"已发布 {batch}（替换 {old or '无'}）")
    neo4j_client.close()
