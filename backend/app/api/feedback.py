"""Record feedback against an existing question request."""

from fastapi import APIRouter

from app.core.errors import ApiError, ErrorCode
from app.schemas.resources import FeedbackIn
from app.storage import sqlite

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=201)
def create_feedback(body: FeedbackIn) -> dict:
    with sqlite.connect() as conn:
        if not conn.execute(
            "SELECT 1 FROM qa_logs WHERE request_id=?", (body.request_id,)
        ).fetchone():
            raise ApiError(404, ErrorCode.NOT_FOUND, "Request not found")
        conn.execute(
            "INSERT INTO feedback(request_id,type,comment) VALUES (?,?,?)",
            (body.request_id, body.type, body.comment),
        )
    return {"saved": True}
