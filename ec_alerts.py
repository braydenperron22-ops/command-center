"""Environment Canada public weather alerts (special weather statements,
warnings, watches) for North Bay — free, no API key, no rate limit beyond
being a polite poller. Environment Canada publishes a plain ATOM feed per
alert region at a fixed URL (weather.gc.ca/rss/battleboard/{code}_e.xml);
this is the North Bay - Powassan - Mattawa region.

When nothing is in effect, the feed still returns one entry whose title
is literally "No alerts in effect, <region>" — that's filtered out here
so callers only ever see genuine active alerts.
"""

from xml.etree import ElementTree

import requests
import streamlit as st

import fetch_throttle
from config import EC_ALERT_REGION_CODE

ALERT_URL = f"https://weather.gc.ca/rss/battleboard/{EC_ALERT_REGION_CODE}_e.xml"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
# Feeds weather_alerts_bar.current_severity() -> govee_lighting's
# extreme_weather override, the one thing meant to wake someone for a
# real tornado/hurricane/tsunami warning — kept short (was 15 min) so a
# freshly-issued warning reaches that override promptly. No real rate
# limit here per EC (see module docstring) to weigh against that.
CACHE_TTL_SECONDS = 3 * 60

_last_good_alerts: list[dict] | None = None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_alerts_raw() -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(ALERT_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)

    alerts = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
        if not title or title.lower().startswith("no alerts in effect"):
            continue
        summary = (entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").strip()
        alerts.append({"title": title, "summary": summary})
    return alerts


def fetch_alerts() -> list[dict]:
    """Returns active alerts as [{"title": ..., "summary": ...}, ...],
    [] when nothing is genuinely in effect, or the last successfully
    fetched list if this particular refresh failed (same _last_good_X
    fallback pattern every other client in this app already uses —
    the try/except sitting *inside* the cached function used to mean a
    single transient failure got cached as a false "no alerts" for the
    full TTL, silently suppressing a real active warning — including
    one that was already showing — for as long as that bad result
    stayed cached, which is exactly the wrong failure mode for a feed
    that gates a life-safety light override)."""
    global _last_good_alerts
    try:
        result = _fetch_alerts_raw()
    except Exception:
        return _last_good_alerts if _last_good_alerts is not None else []
    _last_good_alerts = result
    return result
