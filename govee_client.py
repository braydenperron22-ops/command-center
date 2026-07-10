"""Thin wrapper over the Govee Developer API (openapi.api.govee.com) —
one HTTP call per capability change. No retry/throttle logic here; that
policy lives in govee_lighting.py since it depends on what the dashboard
is showing, not on anything about the API itself.
"""

import uuid

import requests
import streamlit as st

CONTROL_URL = "https://openapi.api.govee.com/router/api/v1/device/control"


def _api_key() -> str | None:
    return st.secrets.get("GOVEE_API_KEY")


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
        return resp.json().get("code") == 200
    except (requests.RequestException, ValueError):
        # ValueError covers resp.json() failing to parse — Govee returning
        # a non-JSON body (an HTML error page under rate-limiting, a proxy
        # timeout page, etc.) shouldn't be treated any differently than a
        # normal request failure.
        return False


def set_power(device: dict, on: bool) -> bool:
    return _control(device, "devices.capabilities.on_off", "powerSwitch", 1 if on else 0)


def set_color(device: dict, rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return _control(device, "devices.capabilities.color_setting", "colorRgb", (r << 16) + (g << 8) + b)


def set_brightness(device: dict, pct: int) -> bool:
    return _control(device, "devices.capabilities.range", "brightness", max(1, min(100, pct)))
