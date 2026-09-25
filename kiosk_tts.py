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

Voice engine: Kokoro (https://github.com/thewh1teagle/kokoro-onnx),
replacing an earlier Piper-based version. Piper was originally chosen
over the obvious cloud alternatives after checking real pricing
(ElevenLabs' own *API* free tier is 10 credits/month, ~20 characters —
unusable; Google Cloud TTS/Azure Speech both need a billing-enabled
account and key, the same "not actually free/no-key" tradeoff this app
avoids everywhere else) — that reasoning still holds and still rules
those out. Session report, live, after actually hearing Piper's
available English voices (6 candidates originally, then a British
attempt, then a community-trained Jarvis-styled model): every one of
them read as flat/lifeless/"dead" once actually heard aloud — a real
ceiling of Piper's own lightweight architecture, not a bad pick among
its options. Kokoro is a different (still free, still local, still
Apache-2.0/MIT, no account, no key, no per-character cost) engine —
82M params, consistently rated well above Piper's own quality ceiling
in independent comparisons — and the difference was audible
immediately on the same real alert sentence.

Voice: am_echo — picked after listening to 9 real candidates side by
side (4 British Kokoro voices, 4 American Kokoro voices, one VCTK
Piper voice) speaking the kiosk's own real alert sentence, the same
live-pick discipline the original Piper voice was chosen with.

Model file: the int8-quantized build specifically (~92MB, from the
model-files-v1.0 release — a newer v1.1 int8 build exists but runs
114MB, over GitHub's 100MB no-LFS limit) so this can stay committed
directly into the repo the same way the old Piper voice was, rather
than needing Git LFS (real reliability risk: several CI/deploy
platforms don't reliably pull LFS objects without extra configuration
this app has no way to verify against Streamlit Cloud specifically) or
a runtime download (the exact "no persistent disk between redeploys,
first-request download adds real repeated latency" problem the
original Piper choice already rejected). Real cost of the smaller
model: slower synthesis (~3.5s vs ~1.2-2s for the full-precision
build) — acceptable here since this only ever runs once per genuinely
NEW toast (cached 24h after), never in a tight loop; the kiosk box's
own local voice assistant (voice/tts.py) uses the full-precision model
instead, no git-size constraint applies there since that file is
placed directly on the box, never committed.

Needs Python <3.14 (a real kokoro-onnx/onnxruntime incompatibility on
3.14, confirmed live — not just conservative packaging metadata: the
exact same model file throws "Unexpected input data type... expected
tensor(float)" on 3.14 regardless of which quantization variant, and
works cleanly on 3.12). See runtime.txt at the repo root, which pins
Streamlit Cloud to 3.12 for exactly this reason."""

import base64
import io
import wave

import numpy as np
import streamlit as st
from kokoro_onnx import Kokoro

VOICE_MODEL_PATH = "kokoro_voices/kokoro-v1.0.int8.onnx"
VOICES_PATH = "kokoro_voices/voices-v1.0.bin"
KOKORO_VOICE = "am_echo"
KOKORO_LANG = "en-us"

# Confirmed live: ~0.5s one-time model load, ~3.5s to synthesize a full
# alert-length sentence after that (the int8 model — see this module's
# own docstring for why int8 specifically, and why that cost is fine
# here) — still fine to run inline in the same rerun that renders a
# genuinely new toast (the only time this is ever called; see weather_
# alerts_bar._spoken_summary/commute_reminder's own docstrings for the
# one-shot gating that keeps this from re-synthesizing the same toast
# every 5s rerun).
_voice: Kokoro | None = None


def _get_voice() -> Kokoro:
    global _voice
    if _voice is None:
        _voice = Kokoro(VOICE_MODEL_PATH, VOICES_PATH)
    return _voice


def _samples_to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """Kokoro returns raw float32 samples in [-1, 1] at 24kHz (confirmed
    live), not a WAV container the way Piper's own synthesize_wav
    already produced — this is the one bit of glue that didn't exist
    before. Plain 16-bit PCM mono, same shape every consumer of this
    module's own base64 WAV already expects."""
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return buffer.getvalue()


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def synthesize_base64(text: str, length_scale: float | None = None) -> str | None:
    """WAV audio for `text`, base64-encoded — ready to embed directly as
    a data URI (f"data:audio/wav;base64,{this}") in a toast's own HTML,
    for app.py's kiosk script to play via a plain <audio> element
    instead of the browser's own (per-device-inconsistent) speechSynthesis.
    None on any failure (model genuinely missing, a bad input, etc.) —
    callers must fall back to speechSynthesis in that case, the same
    graceful-degradation rule every other real-time fetch in this app
    already follows, not a new one invented for this feature.

    `length_scale` — session request, on the (much longer than any
    prior alert) morning-brief readout specifically: "it talks a little
    fast. Like, it's just trying to get it over with." Kept as the same
    parameter name/contract every existing caller (commute_reminder.py)
    already uses — Piper's own length_scale convention (>1.0 = slower)
    inverted here into Kokoro's `speed` (>1.0 = faster, a plain playback-
    rate multiplier, the opposite convention) so callers never needed to
    change their own numbers when this module switched engines."""
    if not text:
        return None
    try:
        voice = _get_voice()
        speed = 1.0 / length_scale if length_scale is not None else 1.0
        samples, sample_rate = voice.create(text, voice=KOKORO_VOICE, speed=speed, lang=KOKORO_LANG)
        wav_bytes = _samples_to_wav_bytes(samples, sample_rate)
        return base64.b64encode(wav_bytes).decode("ascii")
    except Exception:
        return None
