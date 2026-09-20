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
import logging
import logging.handlers
import os
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

# Real bug found live (see voice/README.md): a small local model, given
# a confused/garbled conversation to work with, sometimes emits the
# literal text "None" as its answer instead of an empty string — a
# known small-model quirk (echoing what a null/missing value would
# print as, rather than actually having nothing to say). `content or
# FALLBACK_ANSWER` alone doesn't catch this: a non-empty string "None"
# is truthy in Python. Checked case-insensitively and stripped, since
# the exact casing/whitespace isn't the point — anything that's
# semantically "no answer" should hit the same fallback.
_EMPTY_ANSWERS = {"", "none", "null", "n/a"}


def _is_empty_answer(text: str | None) -> bool:
    return not text or text.strip().lower() in _EMPTY_ANSWERS

# Real gap found live during testing: voice/status.py only ever holds
# the CURRENT state — the moment a turn finishes and state moves back
# to listening_for_wake_word, whatever was just transcribed/answered is
# gone with no way to check what Jarvis actually heard when a spoken
# answer didn't make sense. This is the fix: every real turn (audio
# mode only — text-mode already echoes both sides to the terminal it's
# run from) gets one line here, transcript and answer together, in a
# plain per-day-rotated log a session can just `tail` or `cat`.
_LOG_DIR = os.path.expanduser("~/.local/state/jarvis-voice")
os.makedirs(_LOG_DIR, exist_ok=True)
_logger = logging.getLogger("jarvis")
_logger.setLevel(logging.INFO)
# "Per-day-rotated" per the comment above, but a plain FileHandler never
# actually rotated -- an always-on kiosk would grow this file forever.
# TimedRotatingFileHandler is what "per-day-rotated" describes: a fresh
# file at local midnight, 14 days kept (matches this app's own 14-day
# retention convention elsewhere, e.g. the learned-notes history) before
# the oldest day is deleted.
_handler = logging.handlers.TimedRotatingFileHandler(
    os.path.join(_LOG_DIR, "conversations.log"), when="midnight", backupCount=14,
)
_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
_logger.addHandler(_handler)


def _system_prompt() -> str:
    parts = [
        f"You are {config.ASSISTANT_NAME}, a voice assistant built into the user's home dashboard.",
        config.PERSONALITY,
    ]
    if dashboard_config is not None and getattr(dashboard_config, "USER_PROFILE", None):
        parts.append("What you know about the user: " + dashboard_config.USER_PROFILE)
    return "\n\n".join(parts)


def run_turn(provider, history: list[dict], user_text: str) -> tuple[str, list[tuple[str, str]]]:
    """One full user turn: appends `user_text`, lets the model call
    tools as many times as it needs (bounded by MAX_TOOL_HOPS), and
    returns (final spoken answer, [(tool_name, tool_result_json), ...]).
    Mutates `history` in place so the conversational follow-up window
    (session requirement: no repeated wake word needed mid-conversation)
    has real prior context to draw on.

    The tool-call list is returned (not just left in `history`)
    specifically so the caller can log it — a real session incident
    (see voice/README.md) had the model claim an answer "came from
    Google Maps" when no such tool exists in this system; being able to
    check afterward whether get_commute_status() was actually called
    for that turn, and what it actually returned, is the difference
    between "the model is fabricating data" and "the model got real
    data and just mislabeled where it came from" — two very different
    problems with very different fixes."""
    history.append({"role": "user", "content": user_text})
    calls_made: list[tuple[str, str]] = []
    for _ in range(MAX_TOOL_HOPS):
        result: ChatResult = provider.chat(history, tools=tools.TOOL_SCHEMAS)
        if not result.tool_calls:
            history.append({"role": "assistant", "content": result.content})
            answer = FALLBACK_ANSWER if _is_empty_answer(result.content) else result.content
            return answer, calls_made
        history.append({
            "role": "assistant",
            "content": result.content,
            "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in result.tool_calls],
        })
        for tc in result.tool_calls:
            tool_result = tools.call_tool(tc.name, tc.arguments)
            calls_made.append((tc.name, tool_result))
            history.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": tool_result})
    return FALLBACK_ANSWER, calls_made


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
        answer, calls_made = run_turn(provider, history, user_text)
        if calls_made:
            print(f"  (tools called: {[name for name, _ in calls_made]})")
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
    history: list[dict] | None = None
    followup_deadline = 0.0
    # A SEPARATE stream/generator from the one record_until_silence
    # uses below — openWakeWord and webrtcvad require genuinely
    # different input chunk sizes (1280 samples/80ms vs. a 10/20/30ms
    # frame; see audio_io.wake_word_frames' own comment for why this
    # isn't a detail worth unifying away). Held open across the whole
    # idle-scanning phase; only actually read from when not in a
    # conversational follow-up window.
    wake_frames = audio_io.wake_word_frames()

    status.set_state("listening_for_wake_word")
    while True:
        if status.is_muted():
            status.set_state("muted")
            time.sleep(0.5)
            continue

        in_followup = history is not None and time.time() < followup_deadline
        if not in_followup:
            if not wake_word.is_wake_word(next(wake_frames)):
                continue
            wake_word.reset()
            history = [{"role": "system", "content": _system_prompt()}]

        # Close the wake-word stream before opening the recording one —
        # never hold two simultaneous InputStreams on the same device.
        # A real-but-minor tradeoff either way: closing first means a
        # brief (sub-100ms) gap where nothing is capturing, which could
        # in principle clip the very start of a command spoken with no
        # pause after the wake word itself; the alternative (leaving
        # both open for the whole recording) risks driver-level
        # contention for the entire multi-second recording instead of a
        # one-time startup gap. Worth tuning once real hardware is
        # available to test against (see voice/README.md) — not
        # something verifiable without a real microphone.
        wake_frames.close()
        status.set_state("listening")
        record_frames = audio_io.mic_frames()
        audio = audio_io.record_until_silence(record_frames)
        record_frames.close()
        text = stt.transcribe(audio)
        wake_frames = audio_io.wake_word_frames()
        if not text:
            _logger.info("heard: (nothing transcribed)")
            status.set_state("listening_for_wake_word")
            history = None
            continue

        status.set_state("processing", detail=text)
        answer, calls_made = run_turn(provider, history, text)
        if calls_made:
            _logger.info(
                "heard: %r -> tools: %s -> answered: %r",
                text,
                [(name, result[:200]) for name, result in calls_made],
                answer,
            )
        else:
            _logger.info("heard: %r -> answered: %r (no tools called)", text, answer)

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
