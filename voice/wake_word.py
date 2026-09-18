"""Local wake-word detection — openWakeWord, fully on-device. This is
the privacy-critical stage: per this project's explicit hard
requirement, audio that doesn't trigger the wake word must never be
transcribed, sent to an LLM, or transmitted anywhere. Everything in
this module runs on raw audio frames already in memory; nothing here
makes a network call.

API verified live against the actual installed package (openwakeword
0.4.0) rather than assumed from memory — three real corrections from
the first draft, each caught by actually running this against real
audio rather than trusting the first version that ran without error:

1. `Model()` takes `wakeword_model_paths` (real file paths), not a
   `wakeword_models` list of bare names, and has no `inference_
   framework` kwarg. `openwakeword.models["hey_jarvis"]["model_path"]`
   is the real lookup.
2. Every pretrained model (including "hey_jarvis") ships bundled
   INSIDE the pip package itself (openwakeword/resources/models/) on
   this version — no `download_models()` call exists, and none is
   needed; confirmed the .onnx files are already on disk immediately
   after `pip install`.
3. THE REAL BUG, found live the first time a human actually spoke to
   this: `model.predict()`'s returned dict is keyed by the model's own
   internal name derived from its filename — "hey_jarvis_v0.1", not
   the bare "hey_jarvis" this module's own WAKE_WORD_MODEL config value
   uses. `prediction.get(config.WAKE_WORD_MODEL, 0.0)` therefore always
   silently returned the 0.0 default, no matter what the model actually
   computed — score() reported a flat 0.0 for real "hey jarvis" speech
   at a clean, verified-good mic level, exactly as it had for a
   synthetic TTS test earlier (which made the earlier test's own 0.0
   read as "expected TTS/human-speech mismatch" instead of the actual
   bug it was hiding). Fixed by reading the dict's own only value
   directly (this module only ever loads ONE wakeword model) instead of
   assuming a key name — robust to whatever openWakeWord happens to
   call it, for any wake word."""

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
    meaningful on its own).

    Reads the ONLY value in the prediction dict rather than looking it
    up by a key name this module assumes — see this module's own
    docstring, point 3, for the real bug that shipped when this instead
    did `prediction.get(config.WAKE_WORD_MODEL, 0.0)`."""
    model = _get_model()
    prediction = model.predict(audio_chunk)
    return float(next(iter(prediction.values()), 0.0))


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
