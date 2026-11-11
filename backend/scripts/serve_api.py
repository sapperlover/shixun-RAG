"""Local API entry point; load this project's .env before importing application config."""

from dotenv import load_dotenv

from app.core.config import REPO_ROOT

if __name__ == "__main__":
    import os

    import uvicorn

    load_dotenv(REPO_ROOT / ".env")
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("API_PORT", "8001")))
