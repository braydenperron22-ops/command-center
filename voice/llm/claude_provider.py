"""Anthropic Claude backend — exists to make good on the session's own
explicit modularity requirement ("AI_PROVIDER=claude... without
rebuilding the entire voice system") with a real, working
implementation rather than just an asserted interface. Not the
default (Ollama is — see voice/config.py), and needs ANTHROPIC_API_KEY
set explicitly to be usable at all; this is an opt-in upgrade path, not
something that silently starts sending queries (or dashboard data, for
questions that pull portfolio/etc.) to a cloud provider.

Only real translation work here is shape conversion: Anthropic's
Messages API takes `system` as a top-level field (not a message role),
and represents tool calls/results as typed content blocks rather than
Ollama's flatter tool_calls list — everything else about the
conversation loop in orchestrator.py is identical regardless of which
provider is active."""

import requests

from voice import config
from voice.llm.base import AIProvider, ChatResult, ToolCall

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
REQUEST_TIMEOUT_SECONDS = 30
MAX_OUTPUT_TOKENS = 400  # a spoken answer is short by design (see voice/config.PERSONALITY) — no need for more


def _to_anthropic_tools(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]


def _to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Splits our generic {"role","content",...} history into (system_text,
    anthropic_messages) — Anthropic has no "system" role in the messages
    array itself. A generic "assistant" message carrying tool_calls
    becomes an assistant turn with tool_use blocks; a generic "tool"
    result message becomes a user turn with a tool_result block —
    Anthropic's own required shape for continuing a tool-use turn."""
    system_parts = []
    out = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_parts.append(m["content"])
        elif role == "tool":
            out.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}],
            })
        elif role == "assistant" and m.get("tool_calls"):
            blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
            blocks += [
                {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]}
                for tc in m["tool_calls"]
            ]
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": role, "content": m["content"]})
    return "\n\n".join(system_parts), out


class ClaudeProvider(AIProvider):
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or config.ANTHROPIC_MODEL
        self.api_key = api_key or config.ANTHROPIC_API_KEY

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        if not self.api_key:
            return ChatResult(content="Claude isn't configured — no ANTHROPIC_API_KEY set.")
        system_text, anthropic_messages = _to_anthropic_messages(messages)
        payload = {
            "model": self.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system_text,
            "messages": anthropic_messages,
        }
        anthropic_tools = _to_anthropic_tools(tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception:
            return ChatResult(content="I couldn't reach Claude just now.")

        text_parts = []
        tool_calls = []
        for block in body.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(id=block["id"], name=block["name"], arguments=block.get("input", {})))
        return ChatResult(content="".join(text_parts), tool_calls=tool_calls)
