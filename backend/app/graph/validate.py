"""批次校验（V1.2 附录 B.2/B.3）：全部通过 → validated；任一失败 → failed（并清理图谱）。

检查项：
- counts：图谱节点/关系数与构建记录一致；
- isolation：没有关系连接两个不同批次的节点（可隔离）；
- whitelist：每条关系的 (起点标签, 类型, 终点标签) 都在白名单内；
- evidence：每条 verified 关系在 SQLite 中至少有一条 verified 证据，且原文块属于本批次（可溯源）；
- citations：每条证据都有 citation_id；
- gold_paths（可选）：给出冻结题集时，每道 expected_status=success 的题，其金标准路径的每条边
  都以 verified 状态存在于本批次。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_whitelist
from app.eval import dataset
from app.storage import neo4j_client, sqlite


def validate(batch_id: str, questions_file: str | Path | None = None) -> dict:
    report: dict[str, dict] = {}
    with sqlite.connect() as conn:
        row = conn.execute(
            "SELECT state, graph_node_count, graph_edge_count FROM build_batches WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
    if row is None or row["state"] != "staging":
        raise ValueError(f"批次 {batch_id} 不存在或不是 staging 状态")

    with neo4j_client.get_driver().session() as s:
        n_nodes = s.run("MATCH (n {batch_id: $b}) RETURN count(n) AS n", b=batch_id).single()["n"]
        n_edges = s.run(
            "MATCH ()-[r {batch_id: $b}]->() RETURN count(r) AS n", b=batch_id
        ).single()["n"]
        report["counts"] = _item(
            n_nodes == row["graph_node_count"] and n_edges == row["graph_edge_count"],
            f"nodes={n_nodes}/{row['graph_node_count']} edges={n_edges}/{row['graph_edge_count']}",
        )
        cross = s.run(
            "MATCH (a)-[r {batch_id: $b}]->(c) "
            "WHERE a.batch_id <> $b OR c.batch_id <> $b RETURN count(r) AS n",
            b=batch_id,
        ).single()["n"]
        report["isolation"] = _item(cross == 0, f"跨批次关系 {cross} 条")

        triples = s.run(
            "MATCH (a)-[r {batch_id: $b}]->(c) "
            "RETURN labels(a)[0] AS a, type(r) AS t, labels(c)[0] AS c, count(*) AS n",
            b=batch_id,
        ).data()
        wl = get_whitelist()
        bad = [
            f"{x['a']}-{x['t']}->{x['c']}" for x in triples if not wl.allows(x["t"], x["a"], x["c"])
        ]
        report["whitelist"] = _item(not bad, f"不在白名单: {bad}" if bad else "全部合法")

        verified = {
            r["rid"]: r
            for r in s.run(
                "MATCH (a)-[r {batch_id: $b, verified: true}]->(c) "
                "RETURN r.relation_id AS rid, a.entity_id AS a, type(r) AS t, c.entity_id AS c",
                b=batch_id,
            ).data()
        }

    with sqlite.connect() as conn:
        ok_rels = {
            r["relation_id"]
            for r in conn.execute(
                "SELECT DISTINCT e.relation_id FROM relation_evidence e "
                "JOIN chunks c ON c.batch_id = e.batch_id AND c.chunk_id = e.chunk_id "
                "WHERE e.batch_id = ? AND e.verification_status = 'verified'",
                (batch_id,),
            )
        }
        no_cit = conn.execute(
            "SELECT count(*) AS n FROM relation_evidence WHERE batch_id = ? AND citation_id IS NULL",
            (batch_id,),
        ).fetchone()["n"]
    lacking = sorted(set(verified) - ok_rels)
    report["evidence"] = _item(
        not lacking, f"{len(verified)} 条 verified 关系；缺少可读回证据: {lacking[:5]}"
    )
    report["citations"] = _item(no_cit == 0, f"缺 citation_id 的证据 {no_cit} 条")

    if questions_file:
        edges = {(v["a"], v["t"], v["c"]) for v in verified.values()}
        missing = []
        for q in dataset.load(Path(questions_file)):
            if q.expected_status != "success":
                continue
            for g in q.gold_relation_path:
                if (g.from_, g.type, g.to) not in edges:
                    missing.append(f"{q.question_id}: {g.from_}-{g.type}->{g.to}")
        report["gold_paths"] = _item(
            not missing, f"金标准边缺失: {missing}" if missing else "全部连通"
        )

    ok = all(v["ok"] for v in report.values())
    with sqlite.connect() as conn:
        conn.execute(
            "UPDATE build_batches SET state = ?, checked_at = datetime('now'), error_json = ? "
            "WHERE batch_id = ?",
            (
                "validated" if ok else "failed",
                None if ok else json.dumps(report, ensure_ascii=False),
                batch_id,
            ),
        )
    if not ok:
        from app.graph.build import drop_graph

        drop_graph(batch_id)
    return {"ok": ok, "checks": report}


def _item(ok: bool, detail: str) -> dict:
    return {"ok": bool(ok), "detail": detail}
