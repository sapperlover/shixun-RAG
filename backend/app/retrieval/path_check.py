"""完整路径判定（V1.2 §1.2、§4.2「任意连通的 2 跳并不等于能回答该问题」、附录 B.3）。

输入：扩展得到的候选路径、Intent（含 mentions）、knowledge_batch。
输出：(通过的路径, 失败原因, 失败跳次)。

逐条检查：
1. 结构：跳数在 [min_hops, max_hops]；全部节点与边的 batch_id 等于本次批次；每条边 verified 且有证据块；
2. 适用范围：路径上的培养方案年级、专业与 scope 一致；
3. 问题语义约束：路径至少包含一个问题提及的实体；若问题提及了某类实体（如“通识选修课”），
   路径上该类节点必须是被提及的那个（防止用“专业选修课”的路径回答“通识选修课”的问题）；
4. 可读回：每条边在 SQLite 中有 verified、属于本批次、可公开访问的原文证据。
全部通过后检查版本冲突：终点为同一条款（doc_id + section）却来自不同 doc_version → VERSION_CONFLICT。

没有路径通过时：若有路径因证据问题失败，返回 EVIDENCE_UNVERIFIED 与跳次；
若全部因语义不相关被排除，返回 (None, None)，由 pipeline 使用扩展阶段记录的断点。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.domain import CandidatePath, Intent
from app.graph import dictionary
from app.storage import evidence


def check_edge_evidence(c: CandidatePath, batch_id: str) -> int | None:
    """返回第一条不合格边的跳次（1 起）；全部合格返回 None。"""
    for i, ev in enumerate(c.evidence, start=1):
        if ev.batch_id != batch_id or not ev.verified or not ev.evidence_chunk_ids:
            return i
    return None


def filter_complete(
    candidates: list[CandidatePath], intent: Intent, batch_id: str
) -> tuple[list[CandidatePath], ErrorCode | None, int | None]:
    cfg = get_settings().retrieval
    mentions = set(intent.mentions)
    entities = dictionary.load(batch_id).entities
    mentioned_labels = {entities[m].label for m in mentions if m in entities}
    readable = evidence.readable_relations(
        batch_id, (e.relation_id for c in candidates for e in c.path.edges)
    )

    ok: list[CandidatePath] = []
    evidence_failure: int | None = None
    for c in candidates:
        if not cfg.min_hops <= c.path.hop_count <= cfg.max_hops:
            continue
        if any(b != batch_id for b in c.node_batches.values()):
            continue
        if not _scope_ok(c, intent) or not _relevant(c, mentions, mentioned_labels):
            continue  # 与问题无关的路径不参与证据判断，避免给出误导性的失败原因
        bad_hop = check_edge_evidence(c, batch_id)
        if bad_hop is None:
            bad_hop = next(
                (i for i, e in enumerate(c.path.edges, 1) if e.relation_id not in readable), None
            )
        if bad_hop is not None:
            evidence_failure = max(evidence_failure or 0, bad_hop)
            continue
        ok.append(c)

    if not ok:
        if evidence_failure:
            return [], ErrorCode.EVIDENCE_UNVERIFIED, evidence_failure
        return [], None, None

    conflict = _version_conflict(ok)
    if conflict:
        return conflict, ErrorCode.VERSION_CONFLICT, None
    return ok, None, None


def _scope_ok(c: CandidatePath, intent: Intent) -> bool:
    s = intent.scope
    for n in c.path.nodes:
        props = c.node_props.get(n.node_id, {})
        if n.label == "ProgramPlan" and s.entry_year and props.get("entry_year") != s.entry_year:
            return False
        if n.label == "Professional" and s.major_code and n.node_id != f"major:{s.major_code}":
            return False
    return True


def _relevant(c: CandidatePath, mentions: set[str], mentioned_labels: set[str]) -> bool:
    if not any(n.node_id in mentions for n in c.path.nodes):
        return False
    for label in mentioned_labels:
        on_path = [n.node_id for n in c.path.nodes if n.label == label]
        if on_path and not any(nid in mentions for nid in on_path):
            return False
    return True


def _version_conflict(paths: list[CandidatePath]) -> list[CandidatePath]:
    by_clause: dict[tuple, dict[str, list[CandidatePath]]] = {}
    for c in paths:
        target = c.path.nodes[-1]
        if target.label != "RuleClause":
            continue
        props = c.node_props.get(target.node_id, {})
        key = (props.get("doc_id"), props.get("section"))
        by_clause.setdefault(key, {}).setdefault(str(props.get("doc_version")), []).append(c)
    for versions in by_clause.values():
        if len(versions) > 1:
            return [c for group in versions.values() for c in group]
    return []
