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
import wave

import numpy as np
import sounddevice as sd
from piper import PiperVoice
from piper.config import SynthesisConfig

from voice import config

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
    failure-modes review: "what happens if text-to-speech fails")."""
    if not text:
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
