"""Local text-to-speech for the voice assistant — reuses the EXACT
Piper voice (en_US-hfc_male-medium) and hand-tuned synthesis parameters
kiosk_tts.py already ships and uses for the dashboard's own toast
alerts, so Jarvis sounds like the same voice, not a second, different-
sounding one. The only real difference from kiosk_tts.py: that module
returns base64 WAV for a browser <audio> element (the dashboard runs on
Streamlit Cloud, nowhere near a speaker); this one plays audio directly
out of this box's own local speaker via sounddevice, since the voice
assistant IS the thing sitting next to the speaker."""

import io
import re
import sys
import time
import wave

import numpy as np
from piper import PiperVoice
from piper.config import SynthesisConfig

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

# Same values kiosk_tts.py's own docstring documents as A/B-tested
# against 6 other voices and picked live — reused verbatim rather than
# re-tuned, so the two surfaces (toast alerts, live conversation) sound
# identical.
_SYNTHESIS_CONFIG = SynthesisConfig(noise_scale=0.5, noise_w_scale=0.5)

_voice: PiperVoice | None = None


def _get_voice() -> PiperVoice:
    global _voice
    if _voice is None:
        _voice = PiperVoice.load(config.PIPER_VOICE_MODEL_PATH, config_path=config.PIPER_VOICE_CONFIG_PATH)
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
    installed yet."""
    if not text:
        return False
    if sd is None:
        print(f"[TTS unavailable — no audio output device] {config.ASSISTANT_NAME} would have said: {text}", file=sys.stderr)
        return False
    try:
        voice = _get_voice()
        buffer = io.BytesIO()
        syn_config = (
            SynthesisConfig(length_scale=length_scale, noise_scale=0.5, noise_w_scale=0.5)
            if length_scale is not None
            else _SYNTHESIS_CONFIG
        )
        with wave.open(buffer, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, syn_config=syn_config)
        buffer.seek(0)
        with wave.open(buffer, "rb") as wav_file:
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_rate = wav_file.getframerate()
            raw = wav_file.readframes(wav_file.getnframes())
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(sample_width, np.int16)
        audio = np.frombuffer(raw, dtype=dtype)
        if n_channels > 1:
            audio = audio.reshape(-1, n_channels)
        sd.play(audio, samplerate=frame_rate)
        sd.wait()
        return True
    except Exception:
        return False


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


# Session report: "make it so the spoken morning brief takes natural
# pauses and doesn't just give me a work sandwich first thing in the
# morning." Piper synthesizes whatever text it's given as ONE
# continuous utterance — there's no way to ask it for inter-sentence
# timing, so a multi-fact paragraph came out as one breathless run-on
# regardless of how many real periods the text had. Splitting on real
# sentence boundaries and inserting a genuine time.sleep() between each
# speak() call is the only way to actually guarantee the pacing, rather
# than hoping punctuation alone shapes Piper's prosody.
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
