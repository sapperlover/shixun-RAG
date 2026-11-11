"""接口层测试（不依赖外部服务）。真实问答链路见 tests/integration。"""

from app.fixtures import MOCK_STATUSES

FULL = {"question": "跨院系选课怎么认定？", "scope": {"major_code": "DEMO01", "entry_year": 2024}}


def test_live(client):
    r = client.get("/health/live")
    assert r.status_code == 200 and r.headers["X-Request-ID"].startswith("req-")


def test_ready_reports_unavailable_services(client):
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["checks"]["neo4j"]["ok"] is False
    assert body["checks"]["sqlite"]["ok"] is True
    assert body["checks"]["active_batch"]["ok"] is False  # 尚未发布批次


def test_ask_without_active_batch_is_503(client):
    r = client.post("/qa/ask", json=FULL)
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "error" and body["error"]["code"] == "NO_ACTIVE_BATCH"
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_ask_too_long_returns_qa_shaped_422(client):
    r = client.post("/qa/ask", json={"question": "x" * 501})
    assert r.status_code == 422
    assert r.json()["status"] == "error" and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "paths" in r.json()


def test_force_status_ignored_outside_dev(client):
    r = client.post("/qa/ask", json=FULL, headers={"X-Debug-Force-Status": "success"})
    assert r.json()["error"]["code"] == "NO_ACTIVE_BATCH"  # 走真实流程


def test_force_status_in_dev(client, dev_env):
    for s in MOCK_STATUSES:
        r = client.post("/qa/ask", json=FULL, headers={"X-Debug-Force-Status": s})
        assert r.json()["status"] == s
        assert r.status_code == (503 if s == "error" else 200)


def test_mock_evidence_readback_in_dev(client, dev_env):
    r = client.get("/evidence/cit-1", params={"knowledge_batch": "batch-demo-01"})
    assert r.status_code == 200 and r.json()["relation_id"] == "rel-demo-0001"


def test_unknown_evidence_is_404(client):
    r = client.get("/evidence/cit-x", params={"knowledge_batch": "batch-none"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_role_guard(client, dev_env):
    assert client.get("/documents").status_code == 200
    r = client.get("/documents", headers={"X-Demo-Role": "knowledge_admin"})
    assert r.status_code == 200 and r.json()["total"] == 0


def test_not_implemented_is_explicit(client, dev_env):
    r = client.post("/documents", headers={"X-Demo-Role": "knowledge_admin"})
    assert r.status_code == 501 and r.json()["error"]["code"] == "NOT_IMPLEMENTED"
