"""模板生成：模型不可用时的降级路径，同时也是生成结果的下限（V1.2 §4.3）。

只复述事实，不引入任何事实之外的数值或结论。answer_mode=template，必须标记 degraded_mode。
TODO(BE, D3)：按题型 T1/T2/T3 写更自然的句式；当前为通用句式。
"""

from __future__ import annotations

from collections import defaultdict

from app.domain import Draft, DraftClaim, FactRecord

_PREDICATE_ZH = {
    "BELONGS_TO": "属于",
    "CONTAINS": "包含",
    "APPLIES_TO": "适用于",
    "CITES": "引用",
    "PREREQUISITE_OF": "是以下课程的先修课：",
}


def render(facts: list[FactRecord], reason: str = "llm_unavailable") -> Draft:
    by_path: dict[str, list[FactRecord]] = defaultdict(list)
    for f in facts:
        by_path[f.path_id].append(f)

    claims: list[DraftClaim] = []
    for i, (path_id, fs) in enumerate(by_path.items(), start=1):
        text = "；".join(
            f"{f.subject}{_PREDICATE_ZH.get(f.predicate, f.predicate)}{f.object}" for f in fs
        )
        claims.append(
            DraftClaim(
                claim_id=f"claim-{i}",
                text=text,
                path_ids=[path_id],
                citation_ids=[f.citation.citation_id for f in fs],
            )
        )
    answer = "\n".join(c.text + " " + "".join(f"[{cid}]" for cid in c.citation_ids) for c in claims)
    return Draft(answer=answer, claims=claims, answer_mode="template", degradation_reason=reason)
