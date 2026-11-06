"""文本向量化（bge-small-zh-v1.5，模型缓存在 MODEL_CACHE_DIR）。

TODO(BE, D3)：在 requirements.in 中加入 sentence-transformers（或 onnx 推理）后实现。
不可用时抛出 ServiceUnavailable，调用方降级为 graph_only。
"""

from __future__ import annotations


def embed(texts: list[str]) -> list[list[float]]:
    raise NotImplementedError("embedding 尚未实现（D3）")
