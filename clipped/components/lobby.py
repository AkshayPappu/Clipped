"""Lobby: room code, live squad, and host setup."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from components.shared import (
    copy_button,
    poll_view,
    primary,
    reconnecting,
    render_players,
    secondary,
)
from services import game_service, room_service
from services.question_bank import load_builtin_prompts
from utils.constants import CATEGORY_LABELS, CATEGORY_ORDER, ROUND_OPTIONS, TIMER_OPTIONS
from utils.session import invite_url


@st.fragment(run_every=timedelta(seconds=1.5))
def lobby_presence() -> None:
    view = poll_view()
    if not view.get("ok"):
        reconnecting()
        return
    render_players(view)
    if not view["you"]["is_host"]:
        st.markdown('<p class="wait">Waiting for the host to start…</p>', unsafe_allow_html=True)


def render_lobby(view: dict) -> None:
    room = view["room"]
    code = room["code"]
    link = invite_url(code)
    st.markdown(
        f"""
        <div class="code-block">
          <div class="code-label">Room code</div>
          <div class="code-value">{code}</div>
          <p class="code-hint">Send this code to your friends.</p>
          <p class="invite-link">{link}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    copy_button(code, "Copy code")
    copy_button(link, "Copy invite link")
    st.markdown(
        '<p class="hint">Copy the invite link. The address bar is your seat, not the invite.</p>',
        unsafe_allow_html=True,
    )
    lobby_presence()
    if view["you"]["is_host"]:
        _host_setup(view)
    from components.shared import leave_button

    leave_button()


def _host_setup(view: dict) -> None:
    room = view["room"]
    _seed_widget("rounds", room["total_rounds"])
    _seed_widget("answer_seconds", room["answer_seconds"])
    _seed_widget("vote_seconds", room["vote_seconds"])
    _seed_widget("pack", list(room["categories"]))
    _seed_widget("order_label", "Random" if room["question_order"] == "random" else "In order")

    st.markdown('<h2 class="section-title">Setup</h2>', unsafe_allow_html=True)
    rounds = st.selectbox("Rounds", list(ROUND_OPTIONS), key="rounds")
    answer_seconds = st.selectbox("Answer timer", list(TIMER_OPTIONS), key="answer_seconds", format_func=lambda n: f"{n} seconds")
    vote_seconds = st.selectbox("Ranking timer", list(TIMER_OPTIONS), key="vote_seconds", format_func=lambda n: f"{n} seconds")
    categories = st.multiselect(
        "Question packs",
        options=list(CATEGORY_ORDER),
        format_func=lambda key: CATEGORY_LABELS[key],
        key="pack",
    )
    order_label = st.radio("Question order", ["Random", "In order"], horizontal=True, key="order_label")
    order = "random" if order_label == "Random" else "sequential"
    ready = _deck_count(categories or [], view.get("custom_prompts") or [])
    warn = "" if ready >= int(rounds) else " — not enough for the rounds you picked"
    st.markdown(f'<p class="hint">{ready} questions ready{warn}.</p>', unsafe_allow_html=True)

    with st.expander("Custom questions"):
        _custom_editor(view)

    if primary("Start game", "start-game"):
        token = st.session_state["token"]
        saved = room_service.update_settings(
            token,
            int(rounds),
            int(answer_seconds),
            int(vote_seconds),
            list(categories or []),
            order,
        )
        if not saved.get("ok"):
            st.error(saved.get("error", "Couldn't save settings."))
            return
        started = game_service.start_game(token)
        if not started.get("ok"):
            st.error(started.get("error", "Couldn't start."))
            return
        st.toast("Cook something up.")
        st.rerun()


def _custom_editor(view: dict) -> None:
    token = st.session_state["token"]
    if st.session_state.pop("_clear_custom", False):
        st.session_state["custom_body"] = ""
    if st.session_state.pop("_clear_import", False):
        st.session_state["import_body"] = ""
    body = st.text_input("New question", key="custom_body", placeholder="Ask something only this group would get")
    if secondary("Add question", "add-custom"):
        result = room_service.save_custom_prompt(token, body)
        if result.get("ok"):
            st.session_state["_clear_custom"] = True
            st.toast("Saved.")
            st.rerun()
        st.error(result.get("error", "Couldn't save that."))

    for prompt in view.get("custom_prompts") or []:
        prompt_id = prompt["id"]
        include_key = f"inc-{prompt_id}"
        if include_key not in st.session_state:
            st.session_state[include_key] = bool(prompt["included"])
        included = st.checkbox(prompt["body"], key=include_key)
        if included != prompt["included"]:
            room_service.set_prompt_included(token, prompt_id, included)
            st.rerun()
        col_edit, col_delete = st.columns(2)
        with col_edit:
            if secondary("Edit", f"edit-btn-{prompt_id}"):
                st.session_state["editing_prompt"] = prompt_id
        with col_delete:
            if secondary("Delete", f"del-{prompt_id}"):
                room_service.delete_custom_prompt(token, prompt_id)
                st.rerun()
        if st.session_state.get("editing_prompt") == prompt_id:
            edit_key = f"edit-{prompt_id}"
            if edit_key not in st.session_state:
                st.session_state[edit_key] = prompt["body"]
            edited = st.text_input("Edit question", key=edit_key)
            if primary("Save edit", f"save-edit-{prompt_id}"):
                result = room_service.save_custom_prompt(token, edited, prompt_id)
                if result.get("ok"):
                    st.session_state["editing_prompt"] = None
                    st.rerun()
                st.error(result.get("error", "Couldn't save that."))

    pasted = st.text_area("Paste questions, one per line", key="import_body", height=120)
    if secondary("Import list", "import-questions"):
        result = room_service.import_prompts(token, pasted)
        if result.get("ok"):
            st.session_state["_clear_import"] = True
            st.toast(f"Added {result.get('added', 0)}.")
            st.rerun()
        st.error(result.get("error", "Couldn't import those."))


def _deck_count(categories: list[str], customs: list[dict]) -> int:
    selected = set(categories)
    builtin = sum(1 for _id, category, _body, _index in load_builtin_prompts() if category in selected)
    custom = sum(1 for prompt in customs if prompt.get("included"))
    return builtin + custom


def _seed_widget(key: str, value) -> None:
    if key not in st.session_state:
        st.session_state[key] = value

