"""Browser seat: query params hold the player token, invite links do not."""

from __future__ import annotations

import os

import streamlit as st

_WIDGET_PREFIXES = ("inc-", "edit-", "answer-", "order-")
_WIDGET_KEYS = {
    "rounds",
    "answer_seconds",
    "vote_seconds",
    "pack",
    "order_label",
    "confirm_end",
    "editing_prompt",
    "custom_body",
    "import_body",
    "phase_key",
    "seen_phase",
}


def remember(token: str, code: str) -> None:
    _clear_widgets()
    st.session_state["token"] = token
    st.session_state["screen"] = "game"
    st.query_params["sid"] = token
    st.query_params["room"] = code


def clear_seat() -> None:
    _clear_widgets()
    st.session_state["token"] = None
    st.session_state["screen"] = "landing"
    st.session_state.pop("boot_error", None)
    for key in ("sid", "room"):
        if key in st.query_params:
            del st.query_params[key]


def query_value(name: str) -> str:
    raw = st.query_params.get(name, "")
    if isinstance(raw, list):
        return raw[0] if raw else ""
    return str(raw or "")


def invite_url(code: str) -> str:
    base = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if not base:
        try:
            base = str(st.secrets.get("APP_BASE_URL", "")).strip().rstrip("/")
        except Exception:
            base = ""
    if not base:
        base = _request_base()
    if base:
        return f"{base}/?room={code}"
    return f"/?room={code}"


def _request_base() -> str:
    try:
        headers = st.context.headers
        host = headers.get("host") or headers.get("Host") or ""
        proto = headers.get("x-forwarded-proto") or headers.get("X-Forwarded-Proto") or "http"
        if host:
            return f"{proto}://{host}"
    except Exception:
        return ""
    return ""


def _clear_widgets() -> None:
    for key in list(st.session_state.keys()):
        if key in _WIDGET_KEYS or key.startswith(_WIDGET_PREFIXES):
            st.session_state.pop(key, None)
