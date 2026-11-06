from app.fixtures import MOCK_STATUSES

FULL = {
    "question": "【模拟】跨院系选课怎么认定？",
    "scope": {"major_code": "DEMO01", "entry_year": 2024},
}


def test_live(client):
    r = client.get("/health/live")
    assert r.status_code == 200 and r.headers["X-Request-ID"].startswith("req-")


def test_ready_reports_unavailable_services(client):
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["checks"]["neo4j"]["ok"] is False
    assert body["checks"]["sqlite"]["ok"] is True
    assert "anchors" in body["stub_modules"]


def test_ask_success_through_pipeline(client):
    r = client.post("/qa/ask", json=FULL)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["request_id"] == r.headers["X-Request-ID"]
    assert body["paths"][0]["edges"][0]["from"]  # 别名 from 正确序列化


def test_ask_needs_context_when_year_missing(client):
    r = client.post("/qa/ask", json={"question": "q", "scope": {"major_code": "DEMO01"}})
    assert r.json()["status"] == "needs_context"
    assert r.json()["missing_fields"] == ["entry_year"]


def test_ask_too_long_returns_qa_shaped_422(client):
    r = client.post("/qa/ask", json={"question": "x" * 501})
    assert r.status_code == 422
    assert r.json()["status"] == "error" and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "paths" in r.json()


def test_force_status_ignored_outside_dev(client):
    r = client.post("/qa/ask", json=FULL, headers={"X-Debug-Force-Status": "error"})
    assert r.json()["status"] == "success"


def test_force_status_in_dev(client, dev_env):
    for s in MOCK_STATUSES:
        r = client.post("/qa/ask", json=FULL, headers={"X-Debug-Force-Status": s})
        assert r.json()["status"] == s
        assert r.status_code == (503 if s == "error" else 200)


def test_evidence_readback(client):
    r = client.get("/evidence/cit-1", params={"knowledge_batch": "batch-demo-01"})
    assert r.status_code == 200 and r.json()["relation_id"] == "rel-demo-0001"
    assert client.get("/evidence/cit-1", params={"knowledge_batch": "other"}).status_code == 404


def test_role_guard(client, dev_env):
    assert client.get("/documents").status_code == 403
    r = client.get("/documents", headers={"X-Demo-Role": "knowledge_admin"})
    assert r.status_code == 200 and r.json()["total"] == 0


def test_not_implemented_is_explicit(client, dev_env):
    r = client.post("/documents", headers={"X-Demo-Role": "knowledge_admin"})
    assert r.status_code == 501 and r.json()["error"]["code"] == "NOT_IMPLEMENTED"
