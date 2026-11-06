import os
import tempfile

import pytest

# 必须在导入 app 之前设置：测试不依赖任何外部服务
_tmp = tempfile.mkdtemp(prefix="graphrag-test-")
os.environ["APP_ENV"] = "test"
os.environ["SQLITE_PATH"] = os.path.join(_tmp, "app.db")
os.environ["NEO4J_URI"] = "bolt://127.0.0.1:1"  # 故意不可达
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"

from app.core.config import get_env  # noqa: E402


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
