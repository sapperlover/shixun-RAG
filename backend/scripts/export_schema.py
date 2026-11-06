"""由 Pydantic 模型导出 contracts/qa_ask.schema.json：python -m scripts.export_schema

改动 app/schemas/qa.py 后必须执行；契约测试会检查该文件是否过期。
"""

import json

from app.core.config import CONTRACTS_DIR
from app.schemas.qa import QARequest, QAResponse

TARGET = CONTRACTS_DIR / "qa_ask.schema.json"


def build() -> dict:
    return {
        "$comment": "由 backend/scripts/export_schema.py 生成，请勿手改",
        "request": QARequest.model_json_schema(by_alias=True),
        "response": QAResponse.model_json_schema(by_alias=True, mode="serialization"),
    }


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    TARGET.write_text(render(), encoding="utf-8")
    print(f"已写入 {TARGET}")
