"""构建 staging 批次（V1.2 §4.1、附录 B.2）。

步骤：新建 build_batches(state=staging) → 写 chunks / relation_evidence → Neo4j MERGE 节点与边
（node_key、relation_id 由 app.graph.ids 生成，均带 batch_id）→ 构建该批次独立的 FAISS 索引。
不在 active 批次上原地修改。

TODO(Data, D2)
"""

from __future__ import annotations


def build_staging(manifest_path: str, relations_csv: str) -> str:
    """返回新的 batch_id。"""
    raise NotImplementedError
