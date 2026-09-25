"""Local text-to-speech for the voice assistant — reuses the EXACT
Kokoro voice (am_echo) kiosk_tts.py already ships and uses for the
dashboard's own toast alerts, so Jarvis sounds like the same voice,
not a second, different-sounding one (see that module's own docstring
for why Kokoro replaced an earlier Piper-based version, and how
am_echo specifically was picked). The only real difference from
kiosk_tts.py: that module returns base64 WAV for a browser <audio>
element (the dashboard runs on Streamlit Cloud, nowhere near a
speaker); this one plays audio directly out of this box's own local
speaker via sounddevice, since the voice assistant IS the thing
sitting next to the speaker.

Model file: the full-precision build here, not kiosk_tts.py's own
int8 one — that module's int8 choice is specifically about staying
under GitHub's 100MB no-LFS commit limit for Streamlit Cloud, a
constraint that doesn't apply here at all (this file is placed
directly on the kiosk box's own disk, scp'd in, never committed to
git — see voice/README.md). Full precision is both higher quality AND
faster to synthesize on this exact hardware (confirmed live: ~1.2-2s
vs ~3.5s for the int8 build) — strictly better on every axis once the
git-size constraint is out of the picture, which matters even more
here than for kiosk_tts.py: a live conversational reply waiting on
synthesis is a much more noticeable delay than a toast that renders
once and gets cached.

Needs Python <3.14 (a real kokoro-onnx/onnxruntime incompatibility,
confirmed live — see kiosk_tts.py's own docstring for the exact
error). This box's system Python is 3.14, so the voice assistant runs
out of its own dedicated .venv-voice (Python 3.12 via uv) rather than
the shared .venv every other box-side service uses — deliberately
kept separate rather than downgrading the shared venv's own Python,
since run_lg_tv_sync.py/run_spoken_morning_brief.py/the kiosk watchdog
are all already working on 3.14 and have no reason to risk disturbing."""

import re
import sys
import time

import numpy as np
from kokoro_onnx import Kokoro

from voice import config

# sounddevice needs the system libportaudio2 shared library, which is a
# genuinely separate, sudo-gated `apt install` step (see voice/README.md)
# — not something pip alone can guarantee. Importing it at module level
# unguarded means a box that hasn't had that one command run yet can't
# even start the orchestrator at all, including --text-mode, which
# needs no speaker-dependent code path except this one. Caught live:
# this exact box, tonight, had openwakeword/faster-whisper/webrtcvad
# all install and work fine while sounddevice raised `OSError:
# PortAudio library not found` at import time. Degrading here (falling
# back to printing the text) instead of crashing matches this
# project's own explicit failure-modes review ("what happens if... the
# speaker disappears") — a missing/removed speaker should be exactly
# this same code path, not a special case.
try:
    import sounddevice as sd
except OSError:
    sd = None

_voice: Kokoro | None = None


def _get_voice() -> Kokoro:
    global _voice
    if _voice is None:
        _voice = Kokoro(config.KOKORO_VOICE_MODEL_PATH, config.KOKORO_VOICES_PATH)
    return _voice


def speak(text: str, length_scale: float | None = None) -> bool:
    """Synthesizes `text` and plays it out the local default output
    device, blocking until playback finishes (the orchestrator's own
    state machine needs to know when SPEAKING has actually ended before
    it can return to listening). Returns False on any failure (model
    missing, no audio device, empty text) rather than raising — a
    failed TTS must degrade to "the assistant went silent this once,"
    never to crashing the whole voice service (see this project's own
    failure-modes review: "what happens if text-to-speech fails").

    No audio output device at all (see this module's own comment on
    `sd`) prints the text to stdout instead of speaking it and returns
    False — real degradation, not a crash, and genuinely useful for
    --text-mode testing on a box that hasn't had libportaudio2
    installed yet.

    `length_scale` — same contract kiosk_tts.py's own synthesize_base64
    already uses (Piper's convention: >1.0 = slower), converted here
    into Kokoro's `speed` (>1.0 = faster, a plain playback-rate
    multiplier — the opposite convention) so both modules agree on
    what a caller's own number means regardless of which one they call."""
    if not text:
        return False
    if sd is None:
        print(f"[TTS unavailable — no audio output device] {config.ASSISTANT_NAME} would have said: {text}", file=sys.stderr)
        return False
    try:
        voice = _get_voice()
        speed = 1.0 / length_scale if length_scale is not None else 1.0
        samples, sample_rate = voice.create(text, voice=config.KOKORO_VOICE, speed=speed, lang=config.KOKORO_LANG)
        # Kokoro already returns float32 samples in [-1, 1] -- sounddevice
        # plays that dtype natively, no WAV-container round-trip needed
        # the way Piper's own synthesize_wav output required.
        sd.play(np.asarray(samples, dtype=np.float32), samplerate=sample_rate)
        sd.wait()
        return True
    except Exception:
        return False


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


# Session report: "make it so the spoken morning brief takes natural
# pauses and doesn't just give me a work sandwich first thing in the
# morning." Neither Piper nor Kokoro synthesizes with real inter-
# sentence timing control of its own — there's no way to ask either
# for pacing, so a multi-fact paragraph comes out as one breathless
# run-on regardless of how many real periods the text had. Splitting
# on real sentence boundaries and inserting a genuine time.sleep()
# between each speak() call is the only way to actually guarantee the
# pacing, rather than hoping punctuation alone shapes the model's own
# prosody.
#
# A NEW function, not a change to speak() itself — this is deliberately
# scoped to the morning brief's own one-shot delivery. voice/
# orchestrator.py's live conversational replies still call speak()
# directly: a quick back-and-forth answer shouldn't get artificial
# pauses stapled onto it just because this one feature wanted them.
MORNING_BRIEF_PAUSE_SECONDS = 0.45


def speak_with_pauses(text: str, pause_seconds: float = MORNING_BRIEF_PAUSE_SECONDS, length_scale: float | None = None) -> bool:
    """Same contract as speak() (blocks until done, returns False on
    total failure) but synthesizes and plays one sentence at a time,
    with `pause_seconds` of real silence between each. Only pauses after
    a sentence that actually played out loud — on a box with no audio
    device, speak() degrades to printing the text and returns False, and
    there's nothing to pace a silent print against."""
    sentences = _split_sentences(text)
    if not sentences:
        return False
    any_ok = False
    for i, sentence in enumerate(sentences):
        played = speak(sentence, length_scale=length_scale)
        any_ok = any_ok or played
        if played and i < len(sentences) - 1:
            time.sleep(pause_seconds)
    return any_ok
