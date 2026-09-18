"""Microphone capture and VAD-bounded recording. This is the other
privacy-critical stage alongside wake_word.py: raw audio only ever
lives in an in-memory numpy buffer on this box, and only the audio
captured AFTER a real wake-word detection ever gets handed to STT (see
orchestrator.py's own loop for the exact boundary).

HARDWARE NOTE (as of this build): the EliteDesk this runs on has no
microphone attached at all yet (confirmed live: `arecord -l` shows only
the unused onboard analog line-in, no USB mic) — see voice/README.md.
Everything in this module is written and syntax-checked, but the live
"does a real spoken wake word actually trigger" path is genuinely
unverified until a mic is connected. orchestrator.py's --text-mode
flag exists specifically so the rest of the pipeline (LLM, tools, TTS)
can be fully exercised and proven correct independent of that gap."""

import time

import numpy as np
import sounddevice as sd
import webrtcvad

from voice import config

_FRAME_SAMPLES = int(config.SAMPLE_RATE * config.FRAME_MS / 1000)  # webrtcvad requires exactly 10/20/30ms frames


def mic_frames():
    """Yields raw int16 mono frames of exactly FRAME_MS duration,
    forever, from the system default input device. A generator (not a
    callback) so the caller's own loop stays in plain, easy-to-follow
    control flow — wake-word scanning and VAD-bounded recording are
    both just "read the next frame and decide.\""""
    with sd.InputStream(
        samplerate=config.SAMPLE_RATE, channels=1, dtype="int16", blocksize=_FRAME_SAMPLES
    ) as stream:
        while True:
            frame, _overflowed = stream.read(_FRAME_SAMPLES)
            yield frame.reshape(-1)


def record_until_silence(frames) -> np.ndarray:
    """Consumes frames from an already-open `frames` generator (see
    mic_frames) starting right after a wake-word trigger, and returns
    the recorded utterance as float32 in [-1, 1] (the shape voice/stt.py
    expects) once VAD detects the user has stopped talking.

    Two safety nets beyond plain VAD, per this project's own failure-
    modes review: MAX_WAIT_FOR_SPEECH_SECONDS (give up if the user never
    actually says anything after the wake word) and MAX_RECORDING_
    SECONDS (a hard cap regardless of VAD, in case VAD itself never
    reports silence — a stuck sensor must never cause an unbounded
    recording)."""
    vad = webrtcvad.Vad(2)  # 0-3, 2 = moderately aggressive; tuned if false-triggers show up in practice
    collected: list[np.ndarray] = []
    started_speaking = False
    silence_frames_needed = max(1, int(config.VAD_SILENCE_MS / config.FRAME_MS))
    silence_run = 0
    start = time.time()

    for frame in frames:
        elapsed = time.time() - start
        is_speech = vad.is_speech(frame.tobytes(), config.SAMPLE_RATE)

        if not started_speaking:
            if is_speech:
                started_speaking = True
                collected.append(frame)
            elif elapsed > config.MAX_WAIT_FOR_SPEECH_SECONDS:
                break
            continue

        collected.append(frame)
        silence_run = silence_run + 1 if not is_speech else 0
        if silence_run >= silence_frames_needed or elapsed > config.MAX_RECORDING_SECONDS:
            break

    if not collected:
        return np.array([], dtype=np.float32)
    audio_int16 = np.concatenate(collected)
    return (audio_int16.astype(np.float32) / 32768.0).clip(-1.0, 1.0)


def mic_available() -> bool:
    """A cheap, real capability check — session's own failure-modes
    review: "what happens if the microphone disappears." Used at
    startup and can be re-checked periodically so a disconnected mic
    degrades to a clear, logged/status-badge condition rather than the
    orchestrator spinning on a dead input stream."""
    try:
        devices = sd.query_devices()
        return any(d.get("max_input_channels", 0) > 0 for d in devices)
    except Exception:
        return False
