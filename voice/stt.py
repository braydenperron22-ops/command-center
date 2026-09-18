"""Local speech-to-text — faster-whisper (CTranslate2), CPU-only, no
audio ever leaves this box. Deliberately the smallest practical model
size by default (see voice/config.STT_MODEL_SIZE) — this only ever
transcribes a single short spoken command, not a long recording, so a
larger model buys accuracy this use case mostly doesn't need at the
cost of latency it does care about."""

import numpy as np
from faster_whisper import WhisperModel

from voice import config

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(config.STT_MODEL_SIZE, device="cpu", compute_type=config.STT_COMPUTE_TYPE)
    return _model


def transcribe(audio: np.ndarray, sample_rate: int = config.SAMPLE_RATE) -> str:
    """`audio` is a 1-D float32 array in [-1, 1] at `sample_rate` (see
    voice/audio_io.py — this is exactly the shape it hands back from a
    completed recording). Returns "" (never raises) on empty audio or
    any transcription failure — an orchestrator that gets "" back
    treats that as "didn't catch that," the same graceful degradation
    every other stage in this pipeline follows."""
    if audio is None or len(audio) == 0:
        return ""
    try:
        model = _get_model()
        segments, _info = model.transcribe(audio, language="en", vad_filter=False, beam_size=1)
        return " ".join(seg.text.strip() for seg in segments).strip()
    except Exception:
        return ""
