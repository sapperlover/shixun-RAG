import os
import tempfile

import pytest

# 必须在导入 app 之前设置。
# 单元测试（默认）：外部服务地址指向不可达端口，保证不依赖、也不误连正在运行的服务。
# 集成测试（INTEGRATION=1，make test-int）：沿用真实 Neo4j 地址。
_tmp = tempfile.mkdtemp(prefix="graphrag-test-")
os.environ["APP_ENV"] = "test"
os.environ["DOCUMENT_RETRIEVAL_ENABLED"] = "false"
os.environ["DEMO_MODE"] = "false"
os.environ["SQLITE_PATH"] = os.path.join(_tmp, "app.db")
os.environ["FAISS_DIR"] = os.path.join(_tmp, "faiss")
if os.environ.get("INTEGRATION") != "1":
    os.environ["NEO4J_URI"] = "bolt://127.0.0.1:1"
    os.environ["LLM_BASE_URL"] = "http://127.0.0.1:1"

from app.core.config import get_env  # noqa: E402


def pytest_collection_modifyitems(config, items):
    if os.environ.get("INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="集成测试：用 make test-int 运行")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def dev_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    get_env.cache_clear()
    yield
    get_env.cache_clear()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
