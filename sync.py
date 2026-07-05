"""Tracks when the macro data cache was last actually refreshed."""

import time

import streamlit as st


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def _sync_epoch() -> float:
    return time.time()


def minutes_since_sync() -> int:
    return int((time.time() - _sync_epoch()) / 60)
