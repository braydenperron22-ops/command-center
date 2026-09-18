"""Local Ollama backend — the default AI_PROVIDER (see voice/config.py's
own comment for why this, and not groq_client.py/gemini_client.py, is
the right default: neither existing dashboard AI client does tool-
calling, and both silently go quiet during dashboard-only quiet
windows that have nothing to do with a live voice query).

Talks to Ollama's own /api/chat over plain HTTP — no ollama Python
package needed, one dependency-free `requests` call, same pattern every
other API client in this codebase (groq_client, gemini_client) already
uses."""

import time
import uuid

import requests

from voice import config
from voice.llm.base import AIProvider, ChatResult, ToolCall

REQUEST_TIMEOUT_SECONDS = 60  # local CPU inference on a tool-calling prompt can genuinely take this long


class OllamaProvider(AIProvider):
    def __init__(self, model: str | None = None, url: str | None = None):
        self.model = model or config.OLLAMA_MODEL
        self.url = (url or config.OLLAMA_URL).rstrip("/")

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        payload = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        try:
            resp = requests.post(f"{self.url}/api/chat", json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            body = resp.json()
        except requests.exceptions.ConnectionError:
            # Ollama itself isn't running (service down, box mid-boot,
            # crashed) — the one failure mode explicitly called out in
            # this project's own failure-modes review as needing a
            # calm, spoken-friendly message rather than a stack trace.
            return ChatResult(content=f"I can't reach my local AI model right now — {config.ASSISTANT_NAME}'s brain seems to be offline.")
        except requests.exceptions.Timeout:
            return ChatResult(content="That's taking longer than it should — try asking again in a moment.")
        except Exception:
            return ChatResult(content="Something went wrong talking to my local AI model.")

        message = body.get("message") or {}
        raw_tool_calls = message.get("tool_calls") or []
        tool_calls = [
            ToolCall(
                id=str(uuid.uuid4()),
                name=(tc.get("function") or {}).get("name", ""),
                arguments=(tc.get("function") or {}).get("arguments", {}) or {},
            )
            for tc in raw_tool_calls
        ]
        return ChatResult(content=message.get("content") or "", tool_calls=tool_calls)


def is_reachable(url: str | None = None, timeout: float = 2.0) -> bool:
    """Quick liveness probe — orchestrator.py uses this at startup so a
    voice service that comes up before Ollama has finished starting
    (both are systemd services on the same box, boot order isn't
    guaranteed) fails with a clear spoken message instead of a
    confusing first-query timeout."""
    try:
        requests.get(f"{(url or config.OLLAMA_URL).rstrip('/')}/api/tags", timeout=timeout)
        return True
    except Exception:
        return False


def wait_until_reachable(url: str | None = None, max_wait_seconds: float = 30.0) -> bool:
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        if is_reachable(url, timeout=2.0):
            return True
        time.sleep(1.0)
    return False
