"""日志：每行带 request_id；对密码、token 等做脱敏（文档-2 §1.3 安全）。"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_REDACT = re.compile(
    r"(?i)(password|passwd|token|secret|authorization|api[_-]?key)(\"?\s*[:=]\s*\"?)([^\s\",}]+)"
)


def new_request_id() -> str:
    return f"req-{uuid.uuid4().hex[:16]}"


def redact(text: str) -> str:
    return _REDACT.sub(r"\1\2***", text)


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.msg = redact(str(record.msg))
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
