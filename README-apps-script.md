# Fully remote setup (no laptop required)

This replaces the laptop-hosted scheduled sync with a serverless one running
entirely on Google's infrastructure, and moves the dashboard to Streamlit
Community Cloud. Nothing in this setup depends on any personal computer
being on.

**Tradeoff, read this first:** this version is rule-based, not AI-judged.
It can't read emails for nuance the way the Claude-powered sync could —
filtering is keyword/sender-pattern matching, calendar-event creation from
email only works for the specific senders coded into `BOOKING_SENDERS`, and
"standing guidance" alerts (like the Ena/CF-clinic example) only fire for
senders/conditions listed in `GUIDANCE_RULES`. The "News" feature is gone
entirely — there was no good rule-based substitute for judging what's
actually significant. Extend the lists in `apps-script/Code.gs` by hand as
new patterns come up; there's no LLM here to infer new ones automatically.

## 1. Set up the Apps Script sync engine

1. Go to [script.google.com](https://script.google.com) → **New project**.
2. Delete the default `myFunction` code, paste in the full contents of
   [`apps-script/Code.gs`](apps-script/Code.gs).
3. Change the `NTFY_TOPIC` constant near the top to something unique and
   hard to guess (e.g. `brayden-cc-7f3a9d2`) — this is your private
   notification channel, anyone who knows the exact topic name can see
   your alerts, so don't use something guessable.
4. Click **Run** on the `runSync` function once. Google will prompt you to
   authorize Gmail and Calendar access for this script — approve it. This
   is a one-time consent, tied to your Google account, not a device.
5. Click the clock icon (**Triggers**) in the left sidebar → **Add Trigger**
   → choose function `runSync`, event source **Time-driven**, type
   **Minutes timer**, every **15 minutes**. Save.
6. Click **Deploy** → **New deployment** → type **Web app** → Execute as
   **Me**, Who has access **Anyone**. Deploy, and copy the Web App URL it
   gives you (looks like `https://script.google.com/macros/s/AKfycb.../exec`).

## 2. Get notifications on your phone

1. Install the [ntfy app](https://ntfy.sh/) (iOS/Android) or just visit
   `https://ntfy.sh/<your-topic-from-step-3-above>` in a mobile browser and
   subscribe.
2. That's it — red-severity alerts and sync-failure notices will show up
   there instead of through Claude's PushNotification.

## 3. Deploy the dashboard to Streamlit Community Cloud

1. Push this repo to GitHub if you haven't already (it already lives at
   `https://github.com/braydenperron22-ops/command-center`).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   GitHub, click **New app**, pick this repo/branch, set the main file to
   `app.py`.
3. Before deploying, open **Advanced settings → Secrets** and add:
   ```toml
   APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycb.../exec"
   ```
   (the URL from step 1.6 above).
4. Deploy. Streamlit Cloud gives you a public URL
   (`https://<something>.streamlit.app`) that works from any device,
   anywhere — no laptop, no local network needed.

## What still works exactly the same

Weather, commute/traffic, market indices, calendar listing with per-event
ETA/leave-by, golf/tee-time weather notes, weather statements, the "leave
now" banner, the animated background, self-healing sync-health tracking.
All of that is pure data/math and needed no rewrite in spirit — just a new
runtime.
