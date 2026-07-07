"""Persists the watchlist tickers to a local JSON file rather than
st.session_state — session state is per-browser-session, so editing the
list from a laptop wouldn't show up on the always-on kiosk display,
which is a separate session entirely. A shared file on disk is visible
to every session hitting this one running app.

Gitignored: this file changes at runtime (via the page's editable input),
it isn't part of the deployed code baseline.
"""

import json
import os

STORE_PATH = os.path.join(os.path.dirname(__file__), "watchlist.json")
DEFAULT_WATCHLIST = ["CCO.TO", "QTUM", "ATD.TO"]


def load() -> list[str]:
    try:
        with open(STORE_PATH) as f:
            data = json.load(f)
        tickers = data.get("tickers")
        return tickers if tickers else list(DEFAULT_WATCHLIST)
    except (FileNotFoundError, json.JSONDecodeError, OSError, KeyError):
        return list(DEFAULT_WATCHLIST)


def save(tickers: list[str]) -> None:
    try:
        with open(STORE_PATH, "w") as f:
            json.dump({"tickers": tickers}, f)
    except OSError:
        pass  # a failed save just means the edit doesn't stick — not worth crashing the page over
