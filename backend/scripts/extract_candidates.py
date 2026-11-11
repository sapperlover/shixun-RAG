"""可选 API 关系抽取；只写待核验候选文件，不改已批准知识包。"""

import argparse
import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv

from app.core.config import REPO_ROOT, get_env
from app.ingest import bundle, extract_llm
from app.ingest.chunk import Chunk

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit("Output already exists; choose a new candidate file")
    load_dotenv(REPO_ROOT / ".env")
    get_env.cache_clear()
    knowledge = bundle.load(args.bundle)
    chunks = [
        Chunk(
            **{k: row[k] for k in Chunk.__dataclass_fields__ if k != "text_sha256"},
            text_sha256=hashlib.sha256(row["text"].encode()).hexdigest(),
        )
        for row in knowledge.chunks
    ]
    candidates = extract_llm.extract(chunks, knowledge.entities)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in candidates), encoding="utf-8"
    )
    print(json.dumps({"candidates": len(candidates), "verified": 0, "published": False}))
