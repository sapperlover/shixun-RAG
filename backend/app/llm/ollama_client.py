"""Compatibility import; all generation now uses the remote chat API."""

from app.llm.chat_api import chat_json, ping

__all__ = ["chat_json", "ping"]
