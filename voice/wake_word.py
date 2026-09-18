"""Local wake-word detection — openWakeWord, fully on-device. This is
the privacy-critical stage: per this project's explicit hard
requirement, audio that doesn't trigger the wake word must never be
transcribed, sent to an LLM, or transmitted anywhere. Everything in
this module runs on raw audio frames already in memory; nothing here
makes a network call.

NOTE: the exact openwakeword.Model() constructor/predict() signature
below is written from its documented API and gets a live sanity check
(see voice/README.md's own verification log) the first time this
actually runs on the box with the package installed — flagged here
rather than silently assumed correct, since a wake-word library's
precise call signature is exactly the kind of detail worth confirming
against the real installed version rather than memory."""

import numpy as np

from voice import config

_model = None


def _get_model():
    global _model
    if _model is None:
        import openwakeword
        from openwakeword.model import Model

        # Pretrained models (including "hey_jarvis") ship separately
        # from the pip package and need a one-time download on first
        # use — safe to call repeatedly, it no-ops once already present.
        openwakeword.utils.download_models()
        _model = Model(wakeword_models=[config.WAKE_WORD_MODEL], inference_framework="onnx")
    return _model


def score(audio_chunk: np.ndarray) -> float:
    """`audio_chunk` is int16 PCM at 16kHz (openWakeWord's own required
    input format — NOT the float32 array voice/stt.py expects; see
    audio_io.py for where each stage gets its own correctly-shaped
    copy). Returns the wake word's confidence score for this chunk
    (openWakeWord keeps its own internal rolling buffer across calls,
    so chunks must be fed in continuously, in order — a single
    out-of-context chunk isn't meaningful on its own)."""
    model = _get_model()
    prediction = model.predict(audio_chunk)
    return float(prediction.get(config.WAKE_WORD_MODEL, 0.0))


def is_wake_word(audio_chunk: np.ndarray) -> bool:
    return score(audio_chunk) >= config.WAKE_WORD_THRESHOLD


def reset() -> None:
    """Clears openWakeWord's internal rolling buffer — call this right
    after a real detection fires, so the same buffered audio that just
    triggered it can't immediately re-trigger a second false detection
    on the very next frame."""
    model = _get_model()
    if hasattr(model, "reset"):
        model.reset()
