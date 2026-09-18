"""The provider-agnostic interface every AI backend implements — session's
own explicit hard requirement: "Do not make the system dependent on one
specific AI provider... AI_PROVIDER=ollama could use a local model...
AI_PROVIDER=claude [later] without rebuilding the entire voice system."

One method, one shape in, one shape out. voice/llm/__init__.get_provider()
picks which concrete class to instantiate based on voice/config.AI_PROVIDER
— nothing else in the orchestrator ever imports a specific provider
directly."""

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    """What any provider's chat() returns, regardless of backend:
    `content` is the assistant's spoken/text reply (may be empty if the
    model chose to call tools instead of answering directly this turn),
    `tool_calls` is the list of tools it wants invoked (empty if none —
    the ordinary case for a direct answer)."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class AIProvider:
    """Subclasses implement chat() only. `messages` is a plain list of
    {"role": "system"|"user"|"assistant"|"tool", "content": str, ...}
    dicts (a tool-result message additionally carries "tool_call_id"
    and "name" — see orchestrator.py's own loop for exactly how those
    get appended). `tools` is voice.tools.TOOL_SCHEMAS, or None for a
    plain no-tools call.

    Must never raise for an ordinary failure (the model's unreachable,
    a request times out, the API key is missing) — return a ChatResult
    with a plain apologetic `content` instead, same "never take the
    pipeline down" rule every dashboard tool already follows. Raising
    is reserved for a genuine programming error, not a runtime
    availability problem."""

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        raise NotImplementedError
