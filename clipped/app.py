"""clipped. — a realtime party game for the group chat."""

from __future__ import annotations

import streamlit as st

from components.leaderboard import render_final, render_leaderboard
from components.lobby import render_lobby
from components.prompt import render_prompt
from components.shared import inject_css, local_banner, primary, secondary, wordmark
from components.voting import render_voting
from services import game_service, room_service
from utils.constants import PHASE_FINAL, PHASE_LEADERBOARD, PHASE_LOBBY, PHASE_PROMPT, PHASE_TOAST, PHASE_VOTING
from utils.session import clear_seat, query_value, remember

st.set_page_config(
    page_title="clipped.",
    page_icon="✦",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    inject_css()
    _bootstrap()
    token = st.session_state.get("token")
    if token:
        _render_game(token)
        return
    prefill = query_value("room")
    screen = st.session_state.get("screen")
    if screen is None and prefill:
        screen = "join"
    if screen == "create":
        _render_create()
    elif screen == "join":
        _render_join(prefill)
    else:
        _render_landing()


def _bootstrap() -> None:
    if st.session_state.get("_boot"):
        return
    st.session_state["_boot"] = True
    sid = query_value("sid")
    if not sid:
        return
    result = game_service.reconnect(sid)
    if result.get("ok"):
        st.session_state["token"] = sid
        st.session_state["screen"] = "game"
        return
    st.session_state["boot_error"] = result.get("error", "Couldn't reconnect.")
    if "sid" in st.query_params:
        del st.query_params["sid"]


def _show_boot_error() -> None:
    error = st.session_state.pop("boot_error", None)
    if error:
        st.error(error)


def _render_landing() -> None:
    wordmark()
    _show_boot_error()
    if primary("Create room", "go-create"):
        st.session_state["screen"] = "create"
        st.rerun()
    if secondary("Join room", "go-join"):
        st.session_state["screen"] = "join"
        st.rerun()


def _render_create() -> None:
    wordmark(compact=True)
    _show_boot_error()
    st.markdown('<h2 class="question">What should we call you?</h2>', unsafe_allow_html=True)
    name = st.text_input("Display name", placeholder="Your name", max_chars=20, label_visibility="collapsed")
    if primary("Create room", "create-room"):
        result = room_service.create_room(name)
        if result.get("ok"):
            remember(result["token"], result["room"]["code"])
            st.toast("You're in.")
            st.rerun()
        st.error(result.get("error", "Couldn't create a room."))
    if secondary("Back", "create-back"):
        st.session_state["screen"] = "landing"
        st.rerun()


def _render_join(prefill: str) -> None:
    wordmark(compact=True)
    _show_boot_error()
    st.markdown('<h2 class="question">Got a code?</h2>', unsafe_allow_html=True)
    if "join_code" not in st.session_state:
        st.session_state["join_code"] = prefill
    code = st.text_input("Room code", key="join_code", placeholder="4829", max_chars=4)
    name = st.text_input("Display name", key="join_name", placeholder="Your name", max_chars=20)
    if primary("Join room", "join-room"):
        result = room_service.join_room(code, name)
        if result.get("ok"):
            remember(result["token"], result["room"]["code"])
            st.toast("You're in.")
            st.rerun()
        st.error(result.get("error", "Couldn't join."))
    if secondary("Back", "join-back"):
        st.session_state["screen"] = "landing"
        st.rerun()


def _render_game(token: str) -> None:
    view = game_service.sync_room(token)
    if not view.get("ok"):
        wordmark(compact=True)
        st.error(view.get("error", "Something went sideways."))
        if secondary("Back to the start", "bail"):
            clear_seat()
            st.rerun()
        return
    phase = view["room"]["status"]
    st.session_state["phase_key"] = f"{phase}:{view['room']['current_round']}"
    previous = st.session_state.get("seen_phase")
    if previous and previous != phase:
        st.toast(PHASE_TOAST.get(phase, "You're in."))
    st.session_state["seen_phase"] = phase
    wordmark(compact=True)
    local_banner(view)
    if phase == PHASE_LOBBY:
        render_lobby(view)
    elif phase == PHASE_PROMPT:
        render_prompt(view)
    elif phase == PHASE_VOTING:
        render_voting()
    elif phase == PHASE_LEADERBOARD:
        render_leaderboard()
    elif phase == PHASE_FINAL:
        render_final()
    else:
        st.error("This room is closed.")
        if secondary("Back to the start", "closed-back"):
            clear_seat()
            st.rerun()


main()
