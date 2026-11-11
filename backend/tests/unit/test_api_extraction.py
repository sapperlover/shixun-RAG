import hashlib
import json

from app.ingest import extract_llm
from app.ingest.bundle import Entity
from app.ingest.chunk import Chunk


def test_api_extraction_keeps_only_known_entities_and_exact_source_spans(monkeypatch):
    text = "2024级培养方案包含通识教育课程。"
    chunk = Chunk("k", "d", "v", 1, 1, "一", text, hashlib.sha256(text.encode()).hexdigest())
    entities = [
        Entity("plan:x", "ProgramPlan", "2024级培养方案"),
        Entity("category:x", "CourseCategory", "通识教育课程"),
    ]
    good = {
        "from_entity_id": "plan:x",
        "to_entity_id": "category:x",
        "type": "CONTAINS",
        "evidence_excerpt": text,
        "confidence": 0.95,
    }
    candidates = [
        good,
        good,
        {**good, "evidence_excerpt": "编造的证据"},
        {**good, "from_entity_id": "unknown"},
        {**good, "type": "INVENTED"},
        {**good, "confidence": -1},
        {**good, "confidence": True},
    ]
    monkeypatch.setattr(
        extract_llm.chat_api, "chat_json", lambda *a: json.dumps({"relations": candidates})
    )
    result = extract_llm.extract([chunk], entities)
    assert len(result) == 1 and result[0]["verification_status"] == "unverified"
    assert result[0]["requires_review"] and result[0]["evidence_chunk_ids"] == ["k"]
