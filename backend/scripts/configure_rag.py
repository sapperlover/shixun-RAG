"""Create local settings without overwriting existing keys or starting services."""

from __future__ import annotations

import secrets
from pathlib import Path

from dotenv import dotenv_values, set_key

from app.core.config import REPO_ROOT


def configure(root: Path) -> list[str]:
    config = root / ".env.rag"
    if not config.exists():
        config.write_text((root / ".env.rag.example").read_text(encoding="utf-8"), encoding="utf-8")
    values = dotenv_values(config)
    if not values.get("NEO4J_PASSWORD"):
        set_key(str(config), "NEO4J_PASSWORD", secrets.token_urlsafe(24), quote_mode="never")
    return [
        k
        for k in (
            "EMBEDDING_BASE_URL",
            "EMBEDDING_API_KEY",
            "EMBEDDING_MODEL",
            "EMBEDDING_DIMENSIONS",
        )
        if not values.get(k)
    ]


if __name__ == "__main__":
    missing = configure(REPO_ROOT)
    print("Local settings prepared; existing settings preserved; secrets not printed.")
    if missing:
        print("Fill these fields in .env.rag: " + ", ".join(missing))
