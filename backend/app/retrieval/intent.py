"""问题解析（V1.2 §4.2：question_intent、anchors、scope）。

输入：问题文本 + 前端传来的 scope。
输出：Intent（题型、缺失的适用范围字段）。实体提及在锚点阶段按批次词典匹配后填入 mentions。

规则：
- 题型由 path_patterns.yaml 中各模式的 keywords 判定；未命中时 pattern=None（按锚点尝试全部模式）；
- 缺失字段按题型的 required_scope 判定；题型未知时按最保守规则要求 major_code 与 entry_year；
- 缺失时 pipeline 返回 needs_context，不默认取某一年的方案。
"""

from __future__ import annotations

from app.core.config import get_patterns
from app.domain import Intent
from app.schemas.qa import Scope

_ALL_SCOPE_FIELDS = ["major_code", "entry_year"]


def parse(question: str, scope: Scope) -> Intent:
    patterns = get_patterns().patterns
    pattern = next(
        (pid for pid, p in patterns.items() if any(k in question for k in p.keywords)), None
    )
    required = patterns[pattern].required_scope if pattern else _ALL_SCOPE_FIELDS
    missing = [f for f in required if getattr(scope, f) in (None, "")]
    return Intent(question=question, scope=scope, pattern=pattern, missing_fields=missing)
