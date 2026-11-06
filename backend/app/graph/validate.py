"""批次校验（V1.2 附录 B.2/B.3）：通过后 state=validated，否则 failed。

必须检查：节点约束；每条 verified 边至少一个可读回的 Chunk；全部节点/边/Chunk/FAISS 的 batch_id 一致；
FAISS 索引元信息；用冻结测试题样本检查标准路径是否连通。

TODO(Data, D2)
"""

from __future__ import annotations


def validate(batch_id: str) -> dict:
    """返回检查报告；任一项失败时把批次标为 failed。"""
    raise NotImplementedError
