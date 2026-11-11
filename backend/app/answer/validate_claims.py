"""断言-引用双向校验（V1.2 §4.3、附录 B.3）。已实现，各模块不得绕过。

对每条 claim：
1. 引用的 citation_id 必须存在于本次事实中；
2. 引用必须覆盖 claim 依赖路径上的每一条 relation_id；
3. claim 中出现的数字（学分、门数、上限等）必须出现在所引原文摘录或所引事实的实体名称中（按完整数字比较）。
不合格的 claim 被删除并记录原因；pipeline 决定重试、降级为模板或返回 insufficient。
"""

from __future__ import annotations

import re

from app.domain import DraftClaim, FactRecord, Validation

_NUM = re.compile(r"\d+(?:\.\d+)?")


def validate(claims: list[DraftClaim], facts: list[FactRecord]) -> Validation:
    by_cit = {f.citation.citation_id: f for f in facts}
    rels_by_path: dict[str, set[str]] = {}
    for f in facts:
        if f.path_id and f.relation_id:
            rels_by_path.setdefault(f.path_id, set()).add(f.relation_id)

    kept: list[DraftClaim] = []
    dropped: dict[str, str] = {}
    for c in claims:
        reason = _check(c, by_cit, rels_by_path)
        if reason:
            dropped[c.claim_id] = reason
        else:
            kept.append(c)
    return Validation(kept=kept, dropped=dropped)


def _check(
    c: DraftClaim, by_cit: dict[str, FactRecord], rels_by_path: dict[str, set[str]]
) -> str | None:
    if not c.citation_ids:
        return "缺少引用"
    unknown = [cid for cid in c.citation_ids if cid not in by_cit]
    if unknown:
        return f"引用不存在: {unknown}"
    if not c.path_ids and any(by_cit[cid].path_id for cid in c.citation_ids):
        return "缺少路径"
    unknown_p = [pid for pid in c.path_ids if pid not in rels_by_path]
    if unknown_p:
        return f"路径不存在: {unknown_p}"
    covered = {by_cit[cid].relation_id for cid in c.citation_ids}
    for pid in c.path_ids:
        missing = rels_by_path[pid] - covered
        if missing:
            return f"未覆盖路径 {pid} 的边: {sorted(missing)}"
    # 允许的数值来源：所引原文摘录 + 所引事实的实体名称（均来自已核验数据）
    allowed = "".join(
        by_cit[cid].citation.excerpt + by_cit[cid].subject + by_cit[cid].object
        for cid in c.citation_ids
    )
    allowed_nums = set(_NUM.findall(allowed))  # 按完整数字比较，避免 "1" 因 "2024" 而通过
    stray = [n for n in _NUM.findall(c.text) if n not in allowed_nums]
    if stray:
        return f"数值未出现在所引原文中: {stray}"
    return None
