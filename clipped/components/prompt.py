"""Prompt phase. The answer box stays outside the polling fragment."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from components.shared import (
    host_end,
    host_skip,
    poll_view,
    primary,
    reconnecting,
    render_progress,
    render_timer,
    show_round_label,
)
from services import game_service


@st.fragment(run_every=timedelta(seconds=1.5))
def prompt_status() -> None:
    view = poll_view()
    if not view.get("ok"):
        reconnecting()
        return
    prompt = view.get("prompt") or {}
    total = view["room"]["answer_seconds"]
    render_timer(view.get("server_now"), prompt.get("deadline"), total)
    render_progress(
        int(prompt.get("submitted_count") or 0),
        int(prompt.get("player_count") or 0),
        "players submitted",
    )
    host_skip(view)
    host_end(view)


def render_prompt(view: dict) -> None:
    prompt = view["prompt"]
    show_round_label(prompt["round_number"], prompt["total_rounds"], prompt.get("category"))
    st.markdown(f'<h2 class="question">{_escape(prompt["question"])}</h2>', unsafe_allow_html=True)
    prompt_status()
    if prompt.get("your_answer"):
        st.markdown(
            f'<div class="locked"><p class="eyebrow">Locked in</p><p>{_escape(prompt["your_answer"])}</p></div>',
            unsafe_allow_html=True,
        )
        return
    _answer_form(view)


def _answer_form(view: dict) -> None:
    round_key = f"answer-{view['room']['id']}-{view['room']['current_round']}"
    with st.form(f"form-{round_key}", clear_on_submit=False):
        text = st.text_area(
            "Your answer",
            key=round_key,
            placeholder="Drop your answer...",
            max_chars=280,
            height=140,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Lock it in", type="primary", width="stretch")
    st.markdown(
        '<p class="hint">Answers stay anonymous until the receipts drop.</p>',
        unsafe_allow_html=True,
    )
    if not submitted:
        return
    result = game_service.submit_answer(st.session_state["token"], text or "")
    if result.get("ok"):
        st.toast("Locked in.")
        st.rerun()
    st.error(result.get("error", "Couldn't lock that in."))


def _escape(value: str) -> str:
    import html

    return html.escape(value or "")
