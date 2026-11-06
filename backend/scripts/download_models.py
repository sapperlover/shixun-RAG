"""预下载 embedding 模型到 MODEL_CACHE_DIR：python -m scripts.download_models"""

from app.core.config import get_env
from app.llm import embedder

if __name__ == "__main__":
    v = embedder.embed(["测试"])
    print(
        f"{get_env().embedding_model} 就绪，维度 {v.shape[1]}，缓存于 {get_env().model_cache_dir}"
    )
