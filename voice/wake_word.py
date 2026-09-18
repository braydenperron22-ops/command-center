"""Local wake-word detection — openWakeWord, fully on-device. This is
the privacy-critical stage: per this project's explicit hard
requirement, audio that doesn't trigger the wake word must never be
transcribed, sent to an LLM, or transmitted anywhere. Everything in
this module runs on raw audio frames already in memory; nothing here
makes a network call.

API verified live against the actual installed package (openwakeword
0.4.0) rather than assumed from memory — two real corrections from the
first draft, caught this way before ever running against real audio:

1. `Model()` takes `wakeword_model_paths` (real file paths), not a
   `wakeword_models` list of bare names, and has no `inference_
   framework` kwarg. `openwakeword.models["hey_jarvis"]["model_path"]`
   is the real lookup.
2. Every pretrained model (including "hey_jarvis") ships bundled
   INSIDE the pip package itself (openwakeword/resources/models/) on
   this version — no `download_models()` call exists, and none is
   needed; confirmed the .onnx files are already on disk immediately
   after `pip install`."""

import numpy as np

from voice import config

_model = None


def _get_model():
    global _model
    if _model is None:
        import openwakeword
        from openwakeword.model import Model

        entry = openwakeword.models.get(config.WAKE_WORD_MODEL)
        if entry is None:
            raise ValueError(
                f"no pretrained openWakeWord model named {config.WAKE_WORD_MODEL!r}; "
                f"available: {sorted(openwakeword.models)}"
            )
        _model = Model(wakeword_model_paths=[entry["model_path"]])
    return _model


def score(audio_chunk: np.ndarray) -> float:
    """`audio_chunk` is int16 PCM at 16kHz, length a multiple of 1280
    samples (80ms) — openWakeWord's own required input granularity;
    see voice/config.WAKE_WORD_CHUNK_SAMPLES and audio_io.wake_word_
    frames(), which is the ONLY audio_io generator sized for this (the
    VAD-oriented mic_frames()/record_until_silence() pair uses a
    different, smaller frame size — the two libraries have genuinely
    different input requirements, not a detail to unify away). Returns
    the wake word's confidence score for this chunk (openWakeWord keeps
    its own internal rolling buffer across calls, so chunks must be fed
    in continuously, in order — a single out-of-context chunk isn't
    meaningful on its own)."""
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
