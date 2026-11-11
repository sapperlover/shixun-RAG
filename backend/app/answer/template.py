"""模板生成：模型不可用或输出不合格时的降级路径（V1.2 §4.3）。

只复述已核验的事实，不引入任何事实之外的数值或结论。answer_mode=template，必须标记 degraded_mode。
每条路径生成一条断言，引用该路径上全部边的证据，天然满足“引用覆盖路径每条边”的约束。
"""

from __future__ import annotations

from collections import defaultdict

from app.domain import Draft, DraftClaim, FactRecord

_SENTENCE = {
    "BELONGS_TO": "{s}属于{o}",
    "CONTAINS": "{s}包含{o}",
    "APPLIES_TO": "{s}适用于{o}",
    "CITES": "{s}引用了{o}",
    "PREREQUISITE_OF": "{s}是{o}的先修课",
}


def render(facts: list[FactRecord], reason: str = "llm_unavailable") -> Draft:
    by_path: dict[str | None, list[FactRecord]] = defaultdict(list)
    for f in facts:
        by_path[f.path_id].append(f)

    claims: list[DraftClaim] = []
    for i, (path_id, fs) in enumerate(by_path.items(), start=1):
        text = "；".join(
            _SENTENCE.get(f.predicate, "{s} {p} {o}").format(s=f.subject, o=f.object, p=f.predicate)
            for f in fs
            if f.path_id
        )
        excerpts = list(dict.fromkeys(f.citation.excerpt.strip() for f in fs))
        source_text = "\n".join(excerpts)
        text = (text + "。\n" if text else "") + "可核对的原文摘录：\n" + source_text
        claims.append(
            DraftClaim(
                claim_id=f"claim-{i}",
                text=text + "。",
                path_ids=[path_id] if path_id else [],
                citation_ids=list(dict.fromkeys(f.citation.citation_id for f in fs)),
            )
        )
    return Draft(
        answer=compose(claims), claims=claims, answer_mode="template", degradation_reason=reason
    )


def compose(claims: list[DraftClaim]) -> str:
    """答案正文只由通过校验的断言拼成（ADR-018），避免正文出现未经校验的内容。"""
    return "\n".join(c.text + "".join(f"[{cid}]" for cid in c.citation_ids) for c in claims)
