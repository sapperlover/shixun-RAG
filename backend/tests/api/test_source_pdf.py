import hashlib

from app.api import documents


def test_original_pdf_requires_batch_membership_and_matching_hash(client, tmp_path, monkeypatch):
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    content = b"%PDF-1.4\nsource-test"
    (raw / "source.pdf").write_bytes(content)
    row = {
        "doc_id": "d",
        "doc_version": "v",
        "source_file": "source.pdf",
        "source_sha256": hashlib.sha256(content).hexdigest(),
    }
    monkeypatch.setattr(documents, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        documents.document_corpus, "rows", lambda batch: [row] if batch == "b" else []
    )
    params = {"knowledge_batch": "b", "doc_version": "v"}
    response = client.get("/documents/d/source", params=params)
    assert response.status_code == 200 and response.content == content
    assert response.headers["content-type"] == "application/pdf"
    assert (
        client.get("/documents/d/source", params={**params, "knowledge_batch": "wrong"}).status_code
        == 404
    )
    (raw / "source.pdf").write_bytes(b"changed")
    assert client.get("/documents/d/source", params=params).status_code == 409
    row["source_file"] = "../outside.pdf"
    assert client.get("/documents/d/source", params=params).status_code == 404
