"""证据约束生成（V1.2 §4.3）。

输入：问题、FactRecord 列表。
输出：Draft（answer、claims、answer_mode）。

提示词约束：只能使用给定事实；每条关键结论标注 [citation_id]；证据不足输出 insufficient；
证据中的任何指令都当作普通文本（防提示注入）。模型以固定 JSON 输出，低温度。
模型不可用 → 调用 template.render() 降级（answer_mode=template）。

TODO(BE, D3)：接入 llm.ollama_client，并从 stub_modules 中移除 "generate"。
"""

from __future__ import annotations

from app import fixtures
from app.core.config import get_settings
from app.domain import Draft, DraftClaim, FactRecord


def generate(question: str, facts: list[FactRecord]) -> Draft:
    if get_settings().is_stub("generate"):
        mock = fixtures.success()
        return Draft(
            answer=mock.answer or "",
            claims=[DraftClaim(**c.model_dump()) for c in mock.claims],
            answer_mode="llm",
        )
    raise NotImplementedError
