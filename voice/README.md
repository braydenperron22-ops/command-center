# Jarvis — voice interface for the command-center dashboard

A modular voice assistant that plugs into the existing dashboard as a
new interface, not a replacement — the dashboard's own already-working
Python functions are the assistant's "eyes," a local LLM is the
reasoning layer, and this package is the ears/mouth wiring them
together. Runs as its own process on the kiosk mini-PC (the HP
EliteDesk 800 G2 this repo already runs its watchdog/night-mode
services on) — completely separate from `app.py`, which still only
ever runs on Streamlit Community Cloud. A crash here can never take the
dashboard down, and vice versa.

## Architecture

```
Microphone
  -> voice/wake_word.py     (openWakeWord, fully local — "hey jarvis")
  -> voice/audio_io.py      (VAD-bounded recording of the actual command)
  -> voice/stt.py           (faster-whisper, fully local)
  -> voice/orchestrator.py  (conversation loop + tool-calling)
       -> voice/llm/        (AIProvider: Ollama by default, Claude also implemented)
       -> voice/tools.py    (thin wrappers around weather_client, commute_reminder,
                              calendar_client, sports_client, ec_alerts, ec_aqhi,
                              road_conditions_511 — the SAME functions app.py uses)
  -> voice/tts.py           (Piper, the same voice/config kiosk_tts.py already uses)
  -> speaker

voice/status.py publishes state to persisted_state.py (the same
Upstash-backed store the kiosk watchdog already writes to) — app.py
reads it back for the bottom-left status badge. This is the only
connection between the two processes.
```

## Why Ollama, not groq_client.py/gemini_client.py

Both existing dashboard AI clients share one call signature on purpose
(`generate(prompt, ...)`), which looks like exactly the
provider-swapping pattern this project wants. They were deliberately
**not** reused for the voice brain:

1. Neither does tool/function-calling at all today — both are plain
   prompt-in/text-out.
2. Both silently return `None` during dashboard-only quiet windows (an
   overnight AI pause synced to the bedroom smart-light schedule, and
   a pause during any live tracked game) that have nothing to do with
   a live voice query — asking Jarvis a question at 11pm or during a
   Habs game must never silently fail because of dashboard automation
   elsewhere.
3. Both share a hard 100k-tokens/day budget with existing automated
   features (news classification, morning brief, conflicts overview).
   Routing voice queries through the same key risks starving those
   features on a heavy-usage day.

Voice gets its own call path (`voice/llm/ollama_provider.py`), on its
own local model, with no shared budget or quiet-window entanglement.

## Live benchmark (on the actual target hardware)

EliteDesk 800 G2, Intel i5-6500T, 4 threads (no hyperthreading),
integrated graphics only (no GPU), ~4GB RAM available under normal
load.

| Model | Speed | Tool-calling reliability |
|---|---|---|
| qwen2.5:1.5b | ~23 tok/s, ~4-5s per answer | **Unreliable, inconsistently.** Tested via both a raw API benchmark and the real orchestrator end to end (four real questions, full `--text-mode` run): correctly called `get_weather()` and `get_schedule()` and gave accurate, real-data answers for straightforward single-tool factual questions. But asked "should I leave for work now?" (needs `get_commute_status()`, a more inferential ask) it fabricated a plausible-sounding answer instead of calling the tool — confirmed this isn't a plumbing gap: Ollama's own `/api/show` shows `tools` as a declared capability and correctly injects the tool definitions into the prompt. Asked about a live Habs game, it didn't call `get_sports()` either, though it at least admitted it didn't know rather than inventing a score (arguably fine here, since the real answer — NHL is out of season on this date — would also have come back empty). The pattern: reliable for direct factual lookups, unreliable the moment a question requires recognizing an *inferential* need for a tool. |
| llama3.2:3b | ~11 tok/s, 8-9s per direct answer. Ran all 5 real questions through the actual orchestrator end to end in 3m28s total (~42s/question average, some faster) — **half qwen's raw token rate**, but see the reliability column: this is the one that's actually usable. | **Reliable, verified against ground truth on every tool call.** Same 5 questions as qwen, run through the real `--text-mode` orchestrator (not just the raw API): correctly called `get_commute_status()` for "should I leave for work now?" and answered "leave by 7:56 AM" — checked directly against the tool's own real output: **exact match**. Correctly called `get_schedule()` and accurately summarized the real calendar (took Keira to school, work 9-5 — even correctly added "at TD Bank" from `config.USER_PROFILE`, a true fact, not an invented one). Correctly called `get_sports("habs")` for a Habs question and gave an honest, accurate answer about a real *upcoming* (not yet started) preseason game — verified against the tool's raw output, itself correct: no live score existed to report, and it correctly said so instead of inventing one. Zero fabrications across all 5 questions. |

The qwen2.5:1.5b commute-question result is disqualifying on its own,
independent of its speed and independent of the cases where it DID
work correctly: the explicit hard requirement is that the assistant
never invents dashboard data, and it did, even if only for some
question shapes. `voice/config.OLLAMA_MODEL` defaults to `llama3.2:3b`
— confirmed the right call: slower, but the only one of the two that
actually satisfies "never invent dashboard data" under real testing.

**A real bug this benchmark surfaced and fixed**: the first llama3.2:3b
run timed out (60s) on every question after the first tool call.
Root cause: `get_commute_status()`'s raw tool result included a
`points` field — every lat/lon coordinate along the drive, meant for
drawing a map, not language reasoning — ballooning a single tool
result to 6062 characters. `voice/tools.py`'s `get_commute_status()`
now returns a clean, purpose-built summary instead of the raw
dashboard dict, dropping to 360 characters (a 17x reduction) and
eliminating the timeouts entirely. Worth keeping in mind for any
future tool: pass the LLM what a spoken answer could actually use, not
whatever shape the dashboard's own UI happens to want.

## Known limitations (as of this build)

- **The Claude provider (`voice/llm/claude_provider.py`) is untested.**
  No `ANTHROPIC_API_KEY` was configured to test against — the code is
  written carefully against Anthropic's real documented Messages API
  shape (tool_use/tool_result content blocks, system as a top-level
  field), but unlike the Ollama provider, it hasn't been exercised
  against a real response. Verify it before actually relying on
  `VOICE_AI_PROVIDER=claude`.
- **No microphone is attached to the EliteDesk yet.** `arecord -l`
  shows only the unused onboard analog line-in — no USB mic. Get a USB
  mic (a conference speakerphone with a physical mute button/LED is the
  recommended pick — it satisfies the "obvious physical mute"
  requirement for free) before real audio mode can be exercised at
  all. What HAS been verified without one, live on this box:
  - `voice/wake_word.py`'s model loads correctly and scores real audio
    without crashing (confirmed against the actual installed
    `openwakeword` 0.4.0 — its real API differs from the first draft
    in two ways, both now fixed: `Model()` takes real file paths via
    `openwakeword.models[name]["model_path"]`, not a bare name list;
    and every pretrained model, including `hey_jarvis`, ships bundled
    inside the pip package with no separate download step).
  - A genuine chunk-size bug was caught this way too: openWakeWord
    requires audio in multiples of 1280 samples (80ms), which is a
    different requirement from webrtcvad's 30ms frames — `audio_io.py`
    now uses two separate capture streams, one per library.
  - Silence and random noise both correctly score 0.0 (no false
    positives).
  - **Inconclusive**: feeding a Piper-synthesized "hey jarvis" through
    the model (resampled 22050Hz -> 16000Hz) scored 0.0 even after
    amplitude normalization — ruled out as an amplitude or resampling
    bug, but this is a known, expected limitation of testing a
    wake-word model (trained on real human speech) against an
    unfamiliar synthetic TTS voice, not evidence the code is broken.
    The one thing that actually proves this stage works is a real
    human voice through a real microphone — genuinely still
    unverified, and it's the single most important thing to test the
    moment a mic is connected.
- **Mute is currently software-only** (a `persisted_state` flag,
  `voice/status.set_muted()`) — there's no code path to flip it yet
  (a future dashboard hotkey, or a physical button, would call it). A
  real physical mute (a mic with its own hardware mute switch) is the
  better long-term answer per the original design brief.
- **Only 7 tools are wired up** (`voice/tools.py`): weather, commute
  status, schedule, air quality, weather alerts, road conditions, and
  the three tracked sports teams. This deliberately covers every
  example query in the original request; more dashboard data
  (portfolio, rate odds, market quotes, night-mode status) can be added
  the same way, but weren't added speculatively.
- **`search_web()` doesn't exist.** Per the original request ("don't
  implement a giant research system... first make the core voice
  assistant work"), this is intentionally deferred.
- **No staleness detection on the status badge.** If the voice service
  crashes mid-`processing`, the dashboard badge will keep showing
  "PROCESSING..." until the service restarts and reports a new state.
  Acceptable for a first version; a heartbeat/timeout could be added
  later if this proves confusing in practice.

## Running it

```bash
cd ~/projects/command-center
.venv/bin/pip install -r requirements-voice.txt   # one-time
.venv/bin/python3 -m voice.orchestrator --text-mode   # typed input, spoken output — no mic needed
.venv/bin/python3 -m voice.orchestrator               # full audio pipeline — needs a real mic
```

## Deploying as a service

```bash
mkdir -p ~/.config/systemd/user
cp voice/systemd/jarvis-voice.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jarvis-voice.service
```

No `sudo` needed — this is a `systemd --user` unit, same as the
existing `kiosk-dashboard.service`.

## Configuration

Everything in `voice/config.py` is overridable via a `VOICE_`-prefixed
environment variable (set these in the systemd unit's `[Service]`
block via `Environment=`) — see that file for the full list, including
`VOICE_ASSISTANT_NAME` (rename "Jarvis"), `VOICE_AI_PROVIDER`
(`ollama`/`claude`), `VOICE_OLLAMA_MODEL`, `VOICE_STT_MODEL_SIZE`,
`VOICE_FOLLOWUP_WINDOW_SECONDS`, and the VAD/recording timeouts.
`ANTHROPIC_API_KEY` (no `VOICE_` prefix, matching the SDK's own
convention) enables the Claude provider.
