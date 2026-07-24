"""Small pieces of state that must survive an actual process restart (a
redeploy, a Streamlit Cloud sleep/wake) — not just multiple browser
sessions within one running process, which module-level globals alone
already solve. Session discovery: "I also got my morning brief twice"
and a duplicate Brent oil push — an earlier fix moved push-notification
dedup from st.session_state (scoped per browser connection) to plain
module-level globals (scoped per process), which fixed duplicate pushes
across reconnects within one running app, but several redeploys in a
row kept resetting those globals right back to "nothing sent yet,"
reproducing the same symptom from a different cause.

Backed by Upstash Redis (a free-tier REST-based key/value store) when
UPSTASH_REDIS_REST_URL/UPSTASH_REDIS_REST_TOKEN are configured in
st.secrets — session request: "make it so the cache is stored on the
cloud and accessible on different devices and make it more
bulletproof." A local JSON file (the original design) survives an
ordinary restart, but not a platform handing this app a genuinely
fresh filesystem on redeploy, and it's only ever readable from the one
container that wrote it — real gaps the user explicitly asked to close.
Every read/write tries Upstash first when configured, and always keeps
the local file in sync too — not for redundancy's own sake, but because
load() falls back to the local file on any Upstash failure (missing
secrets, network blip, Upstash itself down), so that fallback file has
to actually be current or it'd hand back stale data instead of the
real thing. Same "must never take a page down" rule every other client
in this app already follows: a degraded (local-only) cache the app can
still start on beats a hard dependency on one more external service.

One key per JSON file/Redis key, not one shared blob — matches this
app's existing convention of small standalone state files (todo.json,
commute_history.json).

Deliberately NOT a general-purpose cache — no TTL, no size limits,
callers own their own value shape and any pruning it needs (e.g. a
bounded recent-headline-hash list).
"""

import json
import os
import time

import requests
import streamlit as st

_STATE_DIR = os.path.dirname(__file__)
_UPSTASH_TIMEOUT_SECONDS = 5  # a key/value lookup, not an LLM call — should come back fast or not at all
_KEY_PREFIX = "cc:"  # namespaced in case this Redis database is ever shared with something else

# Reachability of the last real Upstash attempt (True/False), and when
# it happened — a side effect of load()/save() calls that already
# happen, not a new network call of its own. None means either not
# configured at all, or genuinely never attempted yet this process.
# Session request: the maintenance page ("D" hotkey/mobile tab) showing
# cloud-cache health without spending an extra command just to check —
# "be command conscious" ruled out a live probe inside a page that
# could plausibly be left open on someone's phone all day.
_last_upstash_ok: bool | None = None
_last_upstash_at: float | None = None


def upstash_status() -> dict:
    """{"configured", "last_ok", "last_at"} — configured is just
    whether the two secrets are present (no network call); last_ok/
    last_at reflect whichever real load()/save() attempt happened most
    recently anywhere in the app, if any yet this process."""
    return {
        "configured": _upstash_config() is not None,
        "last_ok": _last_upstash_ok,
        "last_at": _last_upstash_at,
    }


def _upstash_config() -> tuple[str, str] | None:
    url = st.secrets.get("UPSTASH_REDIS_REST_URL")
    token = st.secrets.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None
    return url, token


def _local_path(key: str) -> str:
    return os.path.join(_STATE_DIR, f".notify_{key}.json")


def _load_local(key: str, default):
    try:
        with open(_local_path(key)) as f:
            return json.load(f)
    except Exception:
        return default


def _save_local(key: str, value) -> None:
    try:
        with open(_local_path(key), "w") as f:
            json.dump(value, f)
    except Exception:
        pass  # best-effort — see save()'s own docstring


def load(key: str, default):
    """Whatever was last saved under `key` — from Upstash if it's
    configured and reachable, otherwise from the local file — or
    `default` if nothing has ever been saved anywhere (first run) or
    every read attempt fails."""
    global _last_upstash_ok, _last_upstash_at
    config = _upstash_config()
    if config:
        url, token = config
        _last_upstash_at = time.time()
        try:
            resp = requests.get(
                f"{url}/get/{_KEY_PREFIX}{key}", headers={"Authorization": f"Bearer {token}"}, timeout=_UPSTASH_TIMEOUT_SECONDS
            )
            resp.raise_for_status()
            raw = resp.json().get("result")
            _last_upstash_ok = True
            if raw is not None:
                return json.loads(raw)
            # A real, reachable Upstash with genuinely no value for this
            # key yet — not a failure, so don't fall through to
            # (possibly stale) local state; an empty cloud is still the
            # authoritative answer once the cloud is actually up.
            return default
        except Exception:
            _last_upstash_ok = False  # Upstash unreachable/misconfigured/malformed reply — fall back to local
    return _load_local(key, default)


def save(key: str, value) -> None:
    """Best-effort — a failed write just means this particular update
    doesn't survive the next restart/device, not a crash. `value` must
    be JSON-serializable as-is; callers own converting anything else
    (dates, sets) to/from a JSON-friendly shape themselves. Always
    writes the local file (cheap, and it's load()'s own fallback path),
    then also writes to Upstash when configured — a failed cloud write
    never raises, same reasoning as the local-only write it used to be."""
    global _last_upstash_ok, _last_upstash_at
    _save_local(key, value)
    config = _upstash_config()
    if not config:
        return
    url, token = config
    _last_upstash_at = time.time()
    try:
        requests.post(
            f"{url}/set/{_KEY_PREFIX}{key}",
            headers={"Authorization": f"Bearer {token}"},
            data=json.dumps(value),
            timeout=_UPSTASH_TIMEOUT_SECONDS,
        )
        _last_upstash_ok = True
    except Exception:
        _last_upstash_ok = False
