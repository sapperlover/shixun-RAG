"""From backend/: python -m examples.retrieve --question '专业课程有哪些修读要求？'"""

import argparse
import json
import uuid

from dotenv import load_dotenv

from app.core.config import REPO_ROOT

if __name__ == "__main__":
    load_dotenv(REPO_ROOT / ".env.rag")
    # Configure the process before the first get_env()/retrieve() call.
    from app.rag import retrieve

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--entry-year", type=int)
    parser.add_argument("--major", help="Chinese programme name; omit when the question names it")
    parser.add_argument(
        "--program-variant", choices=["regular", "international", "second_degree", "joint"]
    )
    args = parser.parse_args()
    scope = {"entry_year": args.entry_year, "major_code": args.major}
    if args.program_variant:
        scope["program_variant"] = args.program_variant
    result = retrieve(args.question, scope, uuid.uuid4().hex)
    print(json.dumps(result.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2))
