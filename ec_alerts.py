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
# Layer 2: the exact same feed (same region, same format) — confirmed
# live this resolves to a genuinely different IP than weather.gc.ca, not
# just a different hostname pointed at the same box. Session request:
# "make them bulletproof layer 2 sources so if one fails the other takes
# over... arguably the most important part of the dashboard, it needs to
# work consistently." A domain/CDN-specific outage on weather.gc.ca alone
# — the realistic failure mode, not all of EC's infrastructure going dark
# at once — no longer takes this feed down with it.
ALERT_URL_FALLBACK = f"https://meteo.gc.ca/rss/battleboard/{EC_ALERT_REGION_CODE}_e.xml"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
# Feeds weather_alerts_bar.current_severity() -> govee_lighting's
# extreme_weather override, the one thing meant to wake someone for a
# real tornado/hurricane/tsunami warning — kept short (was 15 min) so a
# freshly-issued warning reaches that override promptly. No real rate
# limit here per EC (see module docstring) to weigh against that.
CACHE_TTL_SECONDS = 3 * 60

_last_good_alerts: list[dict] | None = None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_alerts_from(url: str) -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)

    alerts = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
        if not title or title.lower().startswith("no alerts in effect"):
            continue
        summary = (entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").strip()
        # EC's own per-entry tag, e.g. "tag:weather.gc.ca,2013-04-16:
        # onrm119_w1:20260728002540" — genuinely unique per real issuance
        # (embeds the issue timestamp), unlike title text alone, which
        # can legitimately recur for a later, different issuance of the
        # same hazard type. Falls back to the title itself on the rare
        # entry missing one, same as before this field existed.
        entry_id = (entry.findtext("atom:id", default="", namespaces=ATOM_NS) or "").strip()
        alerts.append({"title": title, "summary": summary, "id": entry_id or title})
    return alerts


def fetch_alerts() -> list[dict]:
    """Returns active alerts as [{"title": ..., "summary": ..., "id":
    ...}, ...], [] when nothing is genuinely in effect, or the last
    successfully fetched list if this refresh failed on BOTH the
    primary and fallback domains (same _last_good_X pattern every other
    client in this app already uses — the try/except sitting *inside*
    the cached function used to mean a single transient failure got
    cached as a false "no alerts" for the full TTL, silently
    suppressing a real active warning — including one that was already
    showing — for as long as that bad result stayed cached, which is
    exactly the wrong failure mode for a feed that gates a life-safety
    light override and toast alert). Tries ALERT_URL_FALLBACK
    (meteo.gc.ca) whenever the primary domain itself fails — see that
    constant's own comment — before ever falling back to a stale
    cached value."""
    global _last_good_alerts
    try:
        result = _fetch_alerts_from(ALERT_URL)
    except Exception:
        try:
            result = _fetch_alerts_from(ALERT_URL_FALLBACK)
        except Exception:
            return _last_good_alerts if _last_good_alerts is not None else []
    _last_good_alerts = result
    return result
