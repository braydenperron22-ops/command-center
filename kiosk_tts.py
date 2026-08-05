"""Server-side text-to-speech for kiosk voice alerts (severe weather,
leave-in reminders) — session request: "is there a way to have a
streamlit side text to speech... voices on Dell suck... it sounds
different on my dell streamlit kiosk than on my macbook."

The browser's own Web Speech API (SpeechSynthesisUtterance, what this
app used before) speaks with whatever voice the OS itself happens to
have installed — "Aaron" is a macOS-only voice, so the exact same code
produced a genuinely different-sounding (and worse) voice on a Windows
kiosk, since there's no way to install Aaron there at all. Rendering
the actual audio once, server-side, means every kiosk — Mac, Dell,
anything — plays back the identical WAV file regardless of its own OS
or installed voices.

Piper (https://github.com/OHF-Voice/piper1-gpl) was chosen over the
obvious cloud alternatives after checking real pricing: ElevenLabs'
own *API* free tier is 10 credits/month (~20 characters — unusable);
Google Cloud TTS and Azure Speech both have genuinely generous free
tiers (1-4M / 500K characters a month), but both require a billing-
enabled cloud account and API key, the same "not actually free/no-key"
tradeoff this app has avoided everywhere else (Groq over paid options,
free public feeds over paid data APIs). Piper is free, local, offline,
no account, no key, no per-character cost, ever, matching this app's
own established preference.

Voice: en_US-hfc_male-medium (piper_voices/) — picked after listening
to it side by side with 6 other candidates (lessac, ryan, joe, norman,
alan, bryce) speaking the kiosk's own real alert sentence. Committed
directly into the repo (~63MB) rather than downloaded at runtime,
since a fresh Streamlit Cloud container has no persistent disk to
cache it on between redeploys and a first-request download would add
real, repeated latency."""

import base64
import io
import wave

import streamlit as st
from piper import PiperVoice

VOICE_MODEL_PATH = "piper_voices/en_US-hfc_male-medium.onnx"
VOICE_CONFIG_PATH = "piper_voices/en_US-hfc_male-medium.onnx.json"

# Confirmed live: ~0.66s one-time model load, ~0.35s to synthesize a
# full alert-length sentence after that — fast enough to run inline in
# the same rerun that renders a genuinely new toast (the only time this
# is ever called; see weather_alerts_bar._spoken_summary/
# commute_reminder's own docstrings for the one-shot gating that keeps
# this from re-synthesizing the same toast every 5s rerun).
_voice: PiperVoice | None = None


def _get_voice() -> PiperVoice:
    global _voice
    if _voice is None:
        _voice = PiperVoice.load(VOICE_MODEL_PATH, config_path=VOICE_CONFIG_PATH)
    return _voice


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def synthesize_base64(text: str) -> str | None:
    """WAV audio for `text`, base64-encoded — ready to embed directly as
    a data URI (f"data:audio/wav;base64,{this}") in a toast's own HTML,
    for app.py's kiosk script to play via a plain <audio> element
    instead of the browser's own (per-device-inconsistent) speechSynthesis.
    None on any failure (model genuinely missing, a bad input, etc.) —
    callers must fall back to speechSynthesis in that case, the same
    graceful-degradation rule every other real-time fetch in this app
    already follows, not a new one invented for this feature."""
    if not text:
        return None
    try:
        voice = _get_voice()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return None
