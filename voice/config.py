"""Configuration for the voice assistant — session request: "The
personality should live in configuration/system-prompt logic rather
than being hard-coded throughout the application... I may rename the
assistant later, so do not hard-code 'Jarvis' everywhere." Every other
voice/ module reads its tunables from here rather than embedding a
literal, so a rename or a provider swap is a one-file edit.

Every setting below is overridable via an environment variable (the
systemd unit is the natural place to set these for a real deployment)
so nothing here needs code changes for routine tuning.
"""

import os
import sys

# voice/ is a package INSIDE the command-center repo specifically so it
# can import the dashboard's own already-working data modules directly
# (weather_client, commute_reminder, ...) with zero duplication — see
# this project's own architecture writeup. That only works if the repo
# root is on sys.path, which isn't guaranteed depending on how this
# package gets invoked (a plain `python3 voice/orchestrator.py` puts
# voice/ itself on sys.path, not the parent) — inserted explicitly here,
# once, at import time of this module (which every other voice/ module
# imports first), rather than relying on cwd or invocation style.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _env(name: str, default: str) -> str:
    return os.environ.get(f"VOICE_{name}", default)


# --- Identity / personality ------------------------------------------------
ASSISTANT_NAME = _env("ASSISTANT_NAME", "Jarvis")

# openWakeWord's own pretrained model zoo ships "hey_jarvis_v0.1" as one
# of its example wake words — reused as-is rather than training a
# custom one (see this project's own architecture writeup: "do your own
# homework" wasn't asked here, and a custom wake word is real, separate
# training work, not a config knob). Renaming ASSISTANT_NAME does NOT
# retrain the acoustic wake word — that's a real, separate future task,
# called out honestly rather than silently pretended-away.
WAKE_WORD_MODEL = _env("WAKE_WORD_MODEL", "hey_jarvis")
WAKE_WORD_THRESHOLD = float(_env("WAKE_WORD_THRESHOLD", "0.5"))

# Fed into the LLM as the system prompt, alongside config.USER_PROFILE
# (the same personal-context paragraph morning_briefing.py already
# uses) — session request: personality should be "calm, concise,
# helpful, slightly witty... doesn't unnecessarily repeat information...
# doesn't give enormous responses through TTS... clearly distinguishes
# known information from uncertainty."
PERSONALITY = _env(
    "PERSONALITY",
    "Calm, concise, helpful, and a little witty, but never at the expense of a clear "
    "answer. This is a spoken interface, not a chat window: keep answers short — a "
    "sentence or two, not a paragraph, unless the user's question genuinely needs more. "
    "Never repeat back information the user already stated. When you use a tool, treat "
    "its result as ground truth and never contradict or embellish it. If a tool fails or "
    "returns nothing useful, say plainly that you don't have that information right now — "
    "never guess or invent a number, time, or status in its place. Clearly distinguish "
    "what you know from the dashboard, what you know from general knowledge, and what "
    "you genuinely don't know.",
)

# --- AI provider -------------------------------------------------------
# AI_PROVIDER=ollama|claude — see voice/llm/__init__.py's get_provider().
# Deliberately NOT reusing groq_client.py/gemini_client.py's generate()
# despite their matching "same signature, swap the import" convention:
# both silently return None during the dashboard's own overnight
# pause/game-time quiet windows (a real gotcha found during this
# project's own architecture review — a voice query at 11pm or during a
# Habs game must never silently fail just because dashboard automation
# elsewhere wants quiet), and neither does tool/function-calling at all
# today. A cloud provider for voice gets its own dedicated call path
# instead, on its own key, with no shared daily-budget entanglement
# with the dashboard's own AI features.
AI_PROVIDER = _env("AI_PROVIDER", "ollama")

OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434")
# Chosen after a real live benchmark on this exact hardware (EliteDesk
# 800 G2, i5-6500T, 4 threads, no GPU) comparing qwen2.5:1.5b against
# llama3.2:3b — qwen2.5:1.5b was fast (~23 tok/s) but UNRELIABLE at the
# one thing that matters most here: asked "should I leave for work
# now?" with get_commute_status() available, it fabricated a plausible-
# sounding answer instead of calling the tool. That's disqualifying
# regardless of speed (explicit requirement: never invent dashboard
# data). See voice/README.md for the full benchmark numbers.
OLLAMA_MODEL = _env("OLLAMA_MODEL", "llama3.2:3b")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _env("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# --- Speech-to-text ------------------------------------------------------
# faster-whisper model size — "tiny.en"/"base.en" only (no multilingual
# needed). tiny.en is the lower-latency default on this CPU-only,
# 4-thread box; base.en is a straightforward upgrade (one env var) if
# transcription accuracy ever disappoints in practice.
STT_MODEL_SIZE = _env("STT_MODEL_SIZE", "tiny.en")
STT_COMPUTE_TYPE = _env("STT_COMPUTE_TYPE", "int8")

# --- Text-to-speech --------------------------------------------------------
# Reuses the exact voice kiosk_tts.py already ships (en_US-hfc_male-medium,
# already committed in piper_voices/, already hand-tuned) so Jarvis
# sounds like the same voice the dashboard's own toast alerts do.
PIPER_VOICE_MODEL_PATH = os.path.join(_REPO_ROOT, "piper_voices", "en_US-hfc_male-medium.onnx")
PIPER_VOICE_CONFIG_PATH = os.path.join(_REPO_ROOT, "piper_voices", "en_US-hfc_male-medium.onnx.json")

# --- Audio -----------------------------------------------------------------
SAMPLE_RATE = 16000  # required by both openWakeWord and whisper
FRAME_MS = 30  # webrtcvad only accepts 10/20/30ms frames at 16kHz

# Session request: "a sensible timeout so it does not remain actively
# listening indefinitely after a command... after some configurable
# period of silence, it should return to LISTENING FOR WAKE WORD." This
# is the conversational follow-up window (session request: "I don't
# necessarily want to have to say 'Hey Jarvis' before every single
# sentence") — after Jarvis finishes speaking, the mic stays actively
# listening (no wake word needed) for this long before it drops back to
# passive wake-word-only listening.
FOLLOWUP_WINDOW_SECONDS = float(_env("FOLLOWUP_WINDOW_SECONDS", "8"))

# VAD end-of-speech: recording stops once this much continuous silence
# is seen after the user has started speaking.
VAD_SILENCE_MS = int(_env("VAD_SILENCE_MS", "900"))
# Hard safety cap regardless of VAD — a stuck/failed VAD read must never
# cause an unbounded recording.
MAX_RECORDING_SECONDS = float(_env("MAX_RECORDING_SECONDS", "15"))
# If the user hasn't said anything at all (no speech ever detected) this
# long after the wake word, give up and return to passive listening
# rather than waiting forever for a command that isn't coming.
MAX_WAIT_FOR_SPEECH_SECONDS = float(_env("MAX_WAIT_FOR_SPEECH_SECONDS", "6"))

# --- Shared dashboard state (persisted_state.py, Upstash-backed) -----------
# Same "cc:" prefixed shared store the kiosk watchdog / night-mode-sync
# scripts already use — see this project's own architecture writeup for
# why this is the natural, already-proven channel for a status badge
# rather than inventing a new one.
STATUS_KEY = "voice_status"
MUTE_KEY = "voice_mic_muted"
