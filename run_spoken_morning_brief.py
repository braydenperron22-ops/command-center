"""Entry point for the spoken morning brief — checks once a minute
whether today's real trigger_time (spoken_morning_brief.py) has passed
and it hasn't already run today, and if so, generates and speaks it.

Deliberately a plain polling loop, not a precise one-shot scheduled
job: trigger_time() itself can change through the morning as calendar/
commute data refreshes (a shift getting moved, a live commute estimate
coming in), so re-checking regularly is more correct than computing
the time once at process start and sleeping until then.

Run as its own systemd --user service (see systemd/spoken-morning-
brief.service) — genuinely lightweight (no Ollama, no wake-word model,
no microphone; just a periodic calendar/weather check and, once a day,
one real Gemini call plus one Piper synthesis), unlike voice/
orchestrator.py's full pipeline. Safe to auto-start on boot."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import spoken_morning_brief
import weather_client
from config import TIMEZONE
from voice import tts

CHECK_INTERVAL_SECONDS = 60


def _tick() -> None:
    now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    today = now.date()
    if spoken_morning_brief.already_delivered_today(today):
        return
    if not spoken_morning_brief.in_window(now):
        return
    trigger = spoken_morning_brief.trigger_time(now)
    if trigger is None or now < trigger:
        return

    weather = weather_client.fetch_weather()
    text = spoken_morning_brief.generate(now, weather, None)
    if not text:
        return  # try again next tick rather than marking delivered on a real fetch/AI failure
    tts.speak(text)
    spoken_morning_brief.mark_delivered(today)


def main() -> None:
    while True:
        try:
            _tick()
        except Exception:
            pass  # a single bad tick must never kill the loop — try again next interval
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
