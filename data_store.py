"""Reads dashboard state — from a remote Apps Script sync endpoint if
APPS_SCRIPT_URL is configured (fully remote setup), otherwise from the local
state.json file (laptop-hosted setup with a Claude scheduled task)."""
import json
import os

import requests
import streamlit as st

from config import STATE_PATH

EMPTY_STATE = {
    "last_synced": None,
    "weather": None,
    "calendar_events": [],
    "email_highlights": [],
    "alerts": [],
    "commute": None,
    "indices": [],
}


def _apps_script_url() -> str:
    try:
        if "APPS_SCRIPT_URL" in st.secrets:
            return st.secrets["APPS_SCRIPT_URL"]
    except Exception:
        pass
    return os.environ.get("APPS_SCRIPT_URL", "")


def _load_remote(url: str) -> dict:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, json.JSONDecodeError, ValueError):
        # Network hiccup, cold Apps Script instance, or bad payload — never
        # crash the dashboard over it, just show empty state until it recovers.
        return dict(EMPTY_STATE)
    return {**EMPTY_STATE, **data}


def _load_local() -> dict:
    if not STATE_PATH.exists():
        return dict(EMPTY_STATE)
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # A partially-written or corrupted file shouldn't crash the dashboard —
        # fall back to empty state until the next sync overwrites it cleanly.
        return dict(EMPTY_STATE)
    return {**EMPTY_STATE, **data}


def load_state() -> dict:
    url = _apps_script_url()
    if url:
        return _load_remote(url)
    return _load_local()
