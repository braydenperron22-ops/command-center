"""AI_PROVIDER factory — the ONLY place that picks a concrete provider
class. orchestrator.py (and everything else) only ever talks to the
voice.llm.base.AIProvider interface, never a specific backend, so
switching providers is exactly the one-config-value change the session
asked for."""

from voice import config
from voice.llm.base import AIProvider


def get_provider(name: str | None = None) -> AIProvider:
    provider = (name or config.AI_PROVIDER).lower()
    if provider == "ollama":
        from voice.llm.ollama_provider import OllamaProvider

        return OllamaProvider()
    if provider == "claude":
        from voice.llm.claude_provider import ClaudeProvider

        return ClaudeProvider()
    raise ValueError(f"unknown AI_PROVIDER: {provider!r} (expected 'ollama' or 'claude')")
