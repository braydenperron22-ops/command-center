"""Thin wrapper over the Govee Developer API (openapi.api.govee.com) —
one HTTP call per capability change. No retry/throttle logic here; that
policy lives in govee_lighting.py since it depends on what the dashboard
is showing, not on anything about the API itself.
"""

import time
import uuid

import requests
import streamlit as st

import persisted_state

CONTROL_URL = "https://openapi.api.govee.com/router/api/v1/device/control"


def _api_key() -> str | None:
    return st.secrets.get("GOVEE_API_KEY")


def _record_failure(device: dict, instance: str, value, error: str) -> None:
    """Session report: "the smart plug didn't turn on automatically this
    morning like it was supposed to." Before this, a failed control call
    just returned False and govee_lighting.py moved on to retry next
    rerun — fine for a one-tick blip, but if the real cause were
    something that keeps failing (the device losing WiFi, an expired
    key, Govee's own API down for a stretch), there was zero trace of
    it anywhere: "did anything even try, and why did it fail" was
    unanswerable after the fact. Same shape as app.py's own
    toast_render_error, for the same reason. Only written on an actual
    failure, never on the success path, so this costs nothing extra on
    the overwhelming majority of calls that just work."""
    persisted_state.save(
        "govee_control_error",
        {"at": time.time(), "device": device.get("sku"), "capability": instance, "value": value, "error": error},
    )


def _control(device: dict, cap_type: str, instance: str, value) -> bool:
    key = _api_key()
    if not key:
        return False
    body = {
        "requestId": str(uuid.uuid4()),
        "payload": {
            "sku": device["sku"],
            "device": device["device"],
            "capability": {"type": cap_type, "instance": instance, "value": value},
        },
    }
    try:
        resp = requests.post(
            CONTROL_URL,
            json=body,
            headers={"Govee-API-Key": key, "Content-Type": "application/json"},
            timeout=8,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") == 200:
            return True
        _record_failure(device, instance, value, f"Govee returned code {payload.get('code')}: {payload.get('msg')}")
        return False
    except (requests.RequestException, ValueError) as exc:
        # ValueError covers resp.json() failing to parse — Govee returning
        # a non-JSON body (an HTML error page under rate-limiting, a proxy
        # timeout page, etc.) shouldn't be treated any differently than a
        # normal request failure.
        _record_failure(device, instance, value, f"{type(exc).__name__}: {exc}")
        return False


def set_power(device: dict, on: bool) -> bool:
    return _control(device, "devices.capabilities.on_off", "powerSwitch", 1 if on else 0)


def set_color(device: dict, rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return _control(device, "devices.capabilities.color_setting", "colorRgb", (r << 16) + (g << 8) + b)


def set_brightness(device: dict, pct: int) -> bool:
    return _control(device, "devices.capabilities.range", "brightness", max(1, min(100, pct)))
