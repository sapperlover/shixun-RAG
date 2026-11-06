"""骨架阶段的模拟数据来源：contracts/mocks/*.json。

处于 stub 状态的模块（settings.yaml → pipeline.stub_modules）从这里取数据，
保证整条链路在没有真实实现时也能端到端跑通，且输出始终符合契约。
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
