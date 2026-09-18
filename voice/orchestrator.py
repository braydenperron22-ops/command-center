"""Entry point and state machine for the voice assistant. Run as:

    .venv/bin/python3 -m voice.orchestrator            # full audio pipeline
    .venv/bin/python3 -m voice.orchestrator --text-mode  # typed input, spoken output

--text-mode exists because this box currently has no microphone
attached (see voice/audio_io.py's own hardware note) — it exercises the
entire reasoning pipeline (LLM, tool-calling, dashboard data, TTS
playback) end to end, independent of the one piece of hardware that's
still missing. It is a real testing/fallback mode, not a demo stub: the
exact same conversation loop and TOOL_SCHEMAS run either way.

States (see voice/status.py — these get published for the dashboard's
own badge, matching the session's own requested vocabulary):
listening_for_wake_word -> listening -> processing -> speaking -> back
to listening_for_wake_word (or straight back to listening, within
FOLLOWUP_WINDOW_SECONDS, without needing the wake word again)."""

import argparse
import sys
import time

from voice import audio_io, config, status, stt, tools, tts, wake_word
from voice.llm import get_provider
from voice.llm.base import ChatResult

try:
    import config as dashboard_config
except Exception:  # pragma: no cover - the dashboard's own config.py should always import cleanly
    dashboard_config = None

MAX_TOOL_HOPS = 3  # a real safety cap — a model that keeps calling tools forever must not hang the pipeline
FALLBACK_ANSWER = "Sorry, I'm having trouble answering that right now."


def _system_prompt() -> str:
    parts = [
        f"You are {config.ASSISTANT_NAME}, a voice assistant built into the user's home dashboard.",
        config.PERSONALITY,
    ]
    if dashboard_config is not None and getattr(dashboard_config, "USER_PROFILE", None):
        parts.append("What you know about the user: " + dashboard_config.USER_PROFILE)
    return "\n\n".join(parts)


def run_turn(provider, history: list[dict], user_text: str) -> str:
    """One full user turn: appends `user_text`, lets the model call
    tools as many times as it needs (bounded by MAX_TOOL_HOPS), and
    returns the final spoken answer. Mutates `history` in place so the
    conversational follow-up window (session requirement: no repeated
    wake word needed mid-conversation) has real prior context to draw
    on."""
    history.append({"role": "user", "content": user_text})
    for _ in range(MAX_TOOL_HOPS):
        result: ChatResult = provider.chat(history, tools=tools.TOOL_SCHEMAS)
        if not result.tool_calls:
            history.append({"role": "assistant", "content": result.content})
            return result.content or FALLBACK_ANSWER
        history.append({
            "role": "assistant",
            "content": result.content,
            "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in result.tool_calls],
        })
        for tc in result.tool_calls:
            tool_result = tools.call_tool(tc.name, tc.arguments)
            history.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": tool_result})
    return FALLBACK_ANSWER


def _run_text_mode() -> None:
    provider = get_provider()
    history = [{"role": "system", "content": _system_prompt()}]
    print(f"{config.ASSISTANT_NAME} text-mode — type a question ('quit' to exit). Answers are also spoken aloud.")
    while True:
        try:
            user_text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_text or user_text.lower() in ("quit", "exit"):
            break
        status.set_state("processing")
        answer = run_turn(provider, history, user_text)
        print(f"{config.ASSISTANT_NAME}: {answer}")
        status.set_state("speaking")
        tts.speak(answer)
    status.set_state("listening_for_wake_word")


def _run_audio_mode() -> None:
    from voice.llm.ollama_provider import wait_until_reachable

    if config.AI_PROVIDER == "ollama" and not wait_until_reachable():
        print(f"Ollama isn't reachable at {config.OLLAMA_URL} — {config.ASSISTANT_NAME} can't start.", file=sys.stderr)
        tts.speak("I can't start up — my local AI model isn't responding.")
        sys.exit(1)
    if not audio_io.mic_available():
        print("No microphone detected — falling back is not possible in audio mode.", file=sys.stderr)
        tts.speak("I don't see a microphone connected, so I can't listen for my wake word.")
        sys.exit(1)

    provider = get_provider()
    frames = audio_io.mic_frames()
    history: list[dict] | None = None
    followup_deadline = 0.0

    status.set_state("listening_for_wake_word")
    for frame in frames:
        if status.is_muted():
            status.set_state("muted")
            time.sleep(0.5)
            continue

        in_followup = history is not None and time.time() < followup_deadline
        if not in_followup:
            if not wake_word.is_wake_word(frame):
                continue
            wake_word.reset()
            history = [{"role": "system", "content": _system_prompt()}]

        status.set_state("listening")
        audio = audio_io.record_until_silence(frames)
        text = stt.transcribe(audio)
        if not text:
            status.set_state("listening_for_wake_word")
            history = None
            continue

        status.set_state("processing", detail=text)
        answer = run_turn(provider, history, text)

        status.set_state("speaking")
        tts.speak(answer)

        followup_deadline = time.time() + config.FOLLOWUP_WINDOW_SECONDS
        status.set_state("listening_for_wake_word")


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{config.ASSISTANT_NAME} voice assistant")
    parser.add_argument("--text-mode", action="store_true", help="typed input instead of the microphone/wake-word pipeline")
    args = parser.parse_args()
    if args.text_mode:
        _run_text_mode()
    else:
        _run_audio_mode()


if __name__ == "__main__":
    main()
