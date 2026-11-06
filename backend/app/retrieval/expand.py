"""逐跳扩展（V1.2 §4.2：模式白名单扩展；查询模板见附录 A.3）。

输入：锚点、Intent（含 mentions）、knowledge_batch。
输出：Expansion（完整走完某个模式的候选路径、跳级日志、最相关断点、检索模式）。

规则：
- 只按 path_patterns.yaml 的模式逐跳走；每跳一条 Cypher，批量处理上一跳的全部前沿；
- 每条候选边依次检查：成环 → 适用范围（关系与节点上的专业/年级）→ verified → 有证据块；
  不通过的计入 HopLogEntry.pruned[原因]；
- 每跳最多保留 per_hop_candidates 条（含问题提及实体的优先），全局最多 max_paths 条；
- 断点：某条部分路径在第 k 跳全部被剪掉。取“包含问题提及实体、跳次最深”的断点作为失败原因：
  全因未核验/无证据被剪 → EVIDENCE_UNVERIFIED，否则 PATH_INCOMPLETE；无可用起点 → ANCHOR_NOT_FOUND。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.core.config import HopSpec, get_patterns, get_settings
from app.core.errors import ErrorCode
from app.domain import Anchor, CandidatePath, EdgeEvidence, Expansion, HopLogEntry, Intent
from app.graph import dictionary, ids
from app.schemas.qa import Path, PathEdge, PathNode, Scope
from app.storage import faiss_store, neo4j_client

_EVIDENCE_REASONS = {"unverified", "no_evidence"}


@dataclass
class _Partial:
    pattern: str
    nodes: list[PathNode]
    props: dict[str, dict]
    edges: list[PathEdge] = field(default_factory=list)
    evidence: list[EdgeEvidence] = field(default_factory=list)

    @property
    def tail(self) -> str:
        return self.nodes[-1].node_id


def expand(anchors: list[Anchor], intent: Intent, batch_id: str) -> Expansion:
    cfg = get_settings().retrieval
    mode, reason = _retrieval_mode(batch_id)
    d = dictionary.load(batch_id)
    mentions = set(intent.mentions)

    plans: list[tuple[str, list[HopSpec], Anchor]] = []
    for pid, p in get_patterns().patterns.items():
        if intent.pattern and pid != intent.pattern:
            continue
        for a in anchors:
            if a.label == p.anchor_label:
                plans.append((pid, p.hops, a))
            if p.bidirectional and a.label == p.target_label:
                plans.append((pid, p.reversed_hops(), a))
    if not plans:
        return Expansion(
            candidates=[],
            hop_log=[],
            retrieval_mode=mode,
            degradation_reason=reason,
            failed_code=ErrorCode.ANCHOR_NOT_FOUND,
        )

    logs: dict[int, HopLogEntry] = {}
    dead_ends: list[tuple[bool, int, ErrorCode]] = []
    complete: list[_Partial] = []
    for pid, hops, a in plans:
        start = _Partial(
            pid,
            [PathNode(node_id=a.entity_id, label=a.label, name=a.name)],
            {a.entity_id: d.entities[a.entity_id].props if a.entity_id in d.entities else {}},
        )
        frontier = [start]
        for k, hop in enumerate(hops, start=1):
            log = logs.setdefault(k, HopLogEntry(hop=k, candidates_in=0, kept=0))
            rows = _query(hop, [ids.node_key(batch_id, p.tail) for p in frontier], batch_id)
            by_from: dict[str, list[dict]] = defaultdict(list)
            for r in rows:
                by_from[r["from_key"]].append(r)
            log.candidates_in += len(rows)

            nxt: list[_Partial] = []
            for p in frontier:
                reasons: list[str] = []
                survivors = []
                for r in by_from.get(ids.node_key(batch_id, p.tail), []):
                    why = _prune_reason(r, p, hop, intent.scope)
                    if why:
                        reasons.append(why)
                        log.pruned[why] = log.pruned.get(why, 0) + 1
                    else:
                        survivors.append(_extend(p, r, hop, batch_id))
                if not survivors:
                    code = (
                        ErrorCode.EVIDENCE_UNVERIFIED
                        if reasons and set(reasons) <= _EVIDENCE_REASONS
                        else ErrorCode.PATH_INCOMPLETE
                    )
                    dead_ends.append(
                        (_touches(p, _next_ids(by_from, p, batch_id), mentions), k, code)
                    )
                nxt.extend(survivors)

            nxt.sort(key=lambda p: (-sum(n.node_id in mentions for n in p.nodes), p.tail))
            if len(nxt) > cfg.per_hop_candidates:
                log.pruned["per_hop_limit"] = (
                    log.pruned.get("per_hop_limit", 0) + len(nxt) - cfg.per_hop_candidates
                )
                nxt = nxt[: cfg.per_hop_candidates]
            log.kept += len(nxt)
            frontier = nxt
            if not frontier:
                break
        else:
            complete.extend(frontier)

    if len(complete) > cfg.max_paths:
        last = logs[max(logs)]
        last.pruned["max_paths"] = len(complete) - cfg.max_paths
        complete = complete[: cfg.max_paths]

    exp = Expansion(
        candidates=[_to_candidate(p, i, batch_id) for i, p in enumerate(complete, start=1)],
        hop_log=[logs[k] for k in sorted(logs)],
        retrieval_mode=mode,
        degradation_reason=reason,
    )
    if dead_ends:
        _, exp.failed_hop, exp.failed_code = max(dead_ends, key=lambda x: (x[0], x[1]))
    return exp


def _next_ids(by_from: dict[str, list[dict]], p: _Partial, batch_id: str) -> set[str]:
    """该部分路径在本跳尝试过的下一跳节点（判断断点是否与问题提及实体相关）。"""
    return {r["id"] for r in by_from.get(ids.node_key(batch_id, p.tail), [])}


def _touches(p: _Partial, next_ids: set[str], mentions: set[str]) -> bool:
    return any(n.node_id in mentions for n in p.nodes) or bool(next_ids & mentions)


def _query(hop: HopSpec, keys: list[str], batch_id: str) -> list[dict]:
    arrow = f"-[r:{hop.type}]->" if hop.traverse == "forward" else f"<-[r:{hop.type}]-"
    # 标签与关系类型来自已校验的 path_patterns.yaml，可安全拼入
    return neo4j_client.run_read(
        f"UNWIND $keys AS k "
        f"MATCH (a:{hop.from_label} {{node_key: k}}){arrow}(b:{hop.to_label}) "
        f"WHERE r.batch_id = $batch AND b.batch_id = $batch "
        f"RETURN k AS from_key, b.entity_id AS id, b.name AS name, properties(b) AS props, "
        f"r.relation_id AS rid, startNode(r).entity_id AS s, endNode(r).entity_id AS e, "
        f"coalesce(r.verified, false) AS verified, coalesce(r.evidence_chunk_ids, []) AS ev, "
        f"r.major_code AS r_major, r.entry_year AS r_year, r.batch_id AS r_batch "
        f"ORDER BY b.entity_id",
        keys=keys,
        batch=batch_id,
    )


def _prune_reason(r: dict, p: _Partial, hop: HopSpec, scope: Scope) -> str | None:
    if any(n.node_id == r["id"] for n in p.nodes):
        return "cycle"
    if scope.entry_year and r["r_year"] and r["r_year"] != scope.entry_year:
        return "scope_mismatch"
    if scope.major_code and r["r_major"] and r["r_major"] != scope.major_code:
        return "scope_mismatch"
    props = r["props"]
    if hop.to_label == "ProgramPlan":
        if scope.entry_year and props.get("entry_year") != scope.entry_year:
            return "scope_mismatch"
        if scope.major_code and props.get("major_id") != f"major:{scope.major_code}":
            return "scope_mismatch"
    if (
        hop.to_label == "Professional"
        and scope.major_code
        and r["id"] != f"major:{scope.major_code}"
    ):
        return "scope_mismatch"
    if not r["verified"]:
        return "unverified"
    if not r["ev"]:
        return "no_evidence"
    return None


def _extend(p: _Partial, r: dict, hop: HopSpec, batch_id: str) -> _Partial:
    return _Partial(
        p.pattern,
        [*p.nodes, PathNode(node_id=r["id"], label=hop.to_label, name=r["name"])],
        {**p.props, r["id"]: r["props"]},
        [*p.edges, PathEdge(relation_id=r["rid"], type=hop.type, **{"from": r["s"]}, to=r["e"])],
        [
            *p.evidence,
            EdgeEvidence(
                relation_id=r["rid"],
                verified=r["verified"],
                evidence_chunk_ids=list(r["ev"]),
                batch_id=r["r_batch"],
            ),
        ],
    )


def _to_candidate(p: _Partial, i: int, batch_id: str) -> CandidatePath:
    path = Path(path_id=f"cand-{i}", hop_count=len(p.edges), nodes=p.nodes, edges=p.edges)
    return CandidatePath(
        path=path,
        pattern=p.pattern,  # type: ignore[arg-type]
        evidence=p.evidence,
        node_props=p.props,
        node_batches={nid: props.get("batch_id", "") for nid, props in p.props.items()},
    )


def _retrieval_mode(batch_id: str) -> tuple[str, str | None]:
    if not get_settings().retrieval.vector_enabled:
        return "graph_only", "vector_disabled"
    if faiss_store.status(batch_id) != "ready":
        return "graph_only", "faiss_unavailable"
    return "hybrid", None
