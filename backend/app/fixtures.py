"""契约 mock：contracts/mocks/*.json。

用途仅限：开发环境的 X-Debug-Force-Status 联调、mock 批次的原文读回、契约测试。
生产链路不读取这里的任何数据。
"""

from __future__ import annotations

import json
from functools import lru_cache

from app.core.config import CONTRACTS_DIR
from app.schemas.qa import QAResponse

STUB_BATCH = "batch-demo-01"
MOCK_STATUSES = ("success", "needs_context", "insufficient", "error")


@lru_cache
def load_mock(status: str) -> QAResponse:
    if status not in MOCK_STATUSES:
        raise ValueError(f"未知的 mock 状态: {status}")
    with open(CONTRACTS_DIR / "mocks" / f"{status}.json", encoding="utf-8") as f:
        return QAResponse.model_validate(json.load(f))


def success() -> QAResponse:
    return load_mock("success")
