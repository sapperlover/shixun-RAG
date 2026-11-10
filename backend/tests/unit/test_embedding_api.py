import json

import httpx
import numpy as np
import pytest

from app.core.config import EnvSettings
from app.llm import embedder, embedding_api
from app.storage import faiss_store


@pytest.fixture
def api(monkeypatch):
    settings = EnvSettings(
        embedding_provider="api",
        embedding_model="provided-model",
        embedding_base_url="https://embedding.test/v1",
        embedding_api_key="secret-test",
        embedding_dimensions=2,
        embedding_batch_size=2,
        embedding_max_retries=2,
    )
    monkeypatch.setattr(embedding_api, "get_env", lambda: settings)
    monkeypatch.setattr(embedding_api.time, "sleep", lambda seconds: None)
    original = httpx.Client

    def install(handler):
        monkeypatch.setattr(
            embedding_api.httpx,
            "Client",
            lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
        )

    return settings, install


def test_api_batches_reorders_and_normalizes(api):
    _, install = api
    requests = []

    def handler(req):
        assert req.headers["authorization"] == "Bearer secret-test"
        assert str(req.url) == "https://embedding.test/v1/embeddings"
        payload = json.loads(req.content)
        requests.append(payload)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [3, 4]}
                    for i in reversed(range(len(payload["input"])))
                ]
            },
        )

    install(handler)
    result = embedding_api.embed(["a", "b", "c"])
    assert [r["input"] for r in requests] == [["a", "b"], ["c"]]
    assert result.shape == (3, 2) and result.dtype == np.float32
    np.testing.assert_allclose(result, [[0.6, 0.8]] * 3)


@pytest.mark.parametrize("failure", [429, 500, "timeout"])
def test_retries_transient_failures(api, failure):
    _, install = api
    attempts = []

    def handler(req):
        attempts.append(1)
        if len(attempts) == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("timeout", request=req)
            return httpx.Response(failure)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0]}]})

    install(handler)
    assert embedding_api.embed(["a"]).shape == (1, 2)
    assert len(attempts) == 2


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 1, "embedding": [1, 0]}],
        [{"index": 0, "embedding": [0, 0]}],
        [{"index": 0, "embedding": [1, 2, 3]}],
        [{"index": 0, "embedding": [None, 2]}],
    ],
)
def test_invalid_vectors_fail(api, data):
    _, install = api
    install(lambda req: httpx.Response(200, json={"data": data}))
    with pytest.raises(embedding_api.EmbeddingError, match="Invalid embedding"):
        embedding_api.embed(["a"])


def test_nonfinite_and_bad_json(api):
    _, install = api
    for content in ('{"data":[{"index":0,"embedding":[NaN,1]}]}', "not-json"):
        install(lambda req, content=content: httpx.Response(200, content=content))
        with pytest.raises(embedding_api.EmbeddingError):
            embedding_api.embed(["a"])


def test_auth_failure_not_retried_or_leaked(api):
    _, install = api
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401, text="secret-test")

    install(handler)
    with pytest.raises(embedding_api.EmbeddingError) as err:
        embedding_api.embed(["a"])
    assert len(calls) == 1 and "secret-test" not in str(err.value)


def test_retry_exhaustion_and_missing_config(api):
    settings, install = api
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429)

    install(handler)
    with pytest.raises(embedding_api.EmbeddingError, match="429"):
        embedding_api.embed(["a"])
    assert len(calls) == 3
    settings.embedding_api_key = ""
    with pytest.raises(embedding_api.EmbeddingError, match="requires"):
        embedding_api.embed(["a"])


def test_index_model_endpoint_dimension_and_checksum_identity(tmp_path, monkeypatch):
    settings = EnvSettings(
        faiss_dir=str(tmp_path),
        embedding_provider="api",
        embedding_model="provided-model",
        embedding_dimensions=2,
        embedding_base_url="https://embedding.test/v1",
    )
    monkeypatch.setattr(embedder, "get_env", lambda: settings)
    monkeypatch.setattr(faiss_store, "get_env", lambda: settings)
    monkeypatch.setattr(
        embedder, "embed", lambda texts: np.asarray([[1, 0]] * len(texts), dtype="float32")
    )
    faiss_store.build("b", [("a", "Course", "A")])
    assert faiss_store.search("b", "query", 1)[0][0] == "a"
    for field, value in [
        ("embedding_model", "changed"),
        ("embedding_base_url", "https://other.test/v1"),
        ("embedding_dimensions", 3),
    ]:
        original = getattr(settings, field)
        setattr(settings, field, value)
        with pytest.raises(ValueError, match="identity mismatch"):
            faiss_store.search("b", "query", 1)
        setattr(settings, field, original)
    monkeypatch.setattr(embedder, "embed", lambda texts: np.asarray([[1, 0, 0]], dtype="float32"))
    with pytest.raises(ValueError, match="dimensions"):
        faiss_store.search("b", "query", 1)
    (tmp_path / "b/meta.json").write_text("[]", encoding="utf-8")
    assert faiss_store.status("b") == "metadata checksum mismatch"
