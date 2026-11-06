"""问题解析（V1.2 §4.2；文档-2 §4.2(2) 第 1 步）。

输入：问题文本 + 前端传来的 scope。
输出：Intent（题型、实体提及、缺失的适用范围字段）。

规则：问题依赖培养方案而专业/入学年级缺失时，必须返回 missing_fields，
由 pipeline 返回 needs_context；不得默认取某一年的方案。

TODO(BE, D3)：实体词典 + 规则识别题型与实体提及（可选 LLM 辅助）。
当前实现：题型未知（pattern=None）时，按最保守的规则要求 major_code 与 entry_year 都齐全。
"""

from __future__ import annotations

from app.core.config import get_patterns
from app.domain import Intent
from app.schemas.qa import Scope

_ALL_SCOPE_FIELDS = ["major_code", "entry_year"]


def parse(question: str, scope: Scope) -> Intent:
    pattern = None  # TODO(BE, D3): 识别 T1/T2/T3
    required = get_patterns().patterns[pattern].required_scope if pattern else _ALL_SCOPE_FIELDS
    missing = [f for f in required if getattr(scope, f) in (None, "")]
    return Intent(question=question, scope=scope, pattern=pattern, missing_fields=missing)
