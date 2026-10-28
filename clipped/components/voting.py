"""Rank every answer, best at the top. Points come from the server."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from components.shared import (
    esc,
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
def render_voting() -> None:
    view = poll_view()
    if not view.get("ok"):
        reconnecting()
        return
    voting = view.get("voting") or {}
    show_round_label(voting.get("round_number", 1), voting.get("total_rounds", 1), voting.get("category"))
    st.markdown(f'<h2 class="question">{esc(voting.get("question"))}</h2>', unsafe_allow_html=True)
    st.markdown('<p class="eyebrow">Best on top, worst on the bottom</p>', unsafe_allow_html=True)
    render_timer(view.get("server_now"), voting.get("deadline"), view["room"]["vote_seconds"])
    render_progress(
        int(voting.get("rankings_in") or 0),
        int(voting.get("rankings_needed") or 0),
        "rankings in",
    )
    answers = voting.get("answers") or []
    if not answers:
        st.markdown('<p class="hint">No answers landed. Brutal.</p>', unsafe_allow_html=True)
    elif voting.get("your_order"):
        _locked(answers, list(voting["your_order"]))
    else:
        _editor(view, answers)
    host_skip(view)
    host_end(view)


def _editor(view: dict, answers: list[dict]) -> None:
    order_key = f"order-{view['room']['id']}-{view['room']['current_round']}"
    known = {answer["id"]: answer for answer in answers}
    order = list(st.session_state.get(order_key) or [])
    order = [answer_id for answer_id in order if answer_id in known]
    for answer in answers:
        if answer["id"] not in order:
            order.append(answer["id"])
    st.session_state[order_key] = order
    st.markdown(
        '<p class="hint">Use the arrows. Best at the top. The server turns that order into points.</p>',
        unsafe_allow_html=True,
    )
    for index, answer_id in enumerate(order):
        answer = known[answer_id]
        yours = " · Yours" if answer.get("is_own") else ""
        st.markdown(
            f"""
            <div class="answer-card">
              <p class="eyebrow">#{index + 1}{yours}</p>
              <p class="answer-body">{esc(answer["body"])}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        up, down = st.columns(2)
        with up:
            if st.button("Move up", key=f"up-{answer_id}", disabled=index == 0, width="stretch") and index:
                order[index - 1], order[index] = order[index], order[index - 1]
                st.session_state[order_key] = order
                st.rerun()
        with down:
            if (
                st.button("Move down", key=f"down-{answer_id}", disabled=index == len(order) - 1, width="stretch")
                and index < len(order) - 1
            ):
                order[index + 1], order[index] = order[index], order[index + 1]
                st.session_state[order_key] = order
                st.rerun()
    if primary("Lock in this order", "lock-order"):
        result = game_service.submit_ranking(st.session_state["token"], order)
        if not result.get("ok"):
            st.error(result.get("error", "Couldn't save that order."))
            return
        st.rerun()


def _locked(answers: list[dict], order: list[str]) -> None:
    known = {answer["id"]: answer for answer in answers}
    st.markdown('<p class="eyebrow">Locked in</p>', unsafe_allow_html=True)
    for index, answer_id in enumerate(order):
        answer = known.get(answer_id)
        if answer is None:
            continue
        yours = " · Yours" if answer.get("is_own") else ""
        st.markdown(
            f"""
            <div class="answer-card">
              <p class="eyebrow">#{index + 1}{yours}</p>
              <p class="answer-body">{esc(answer["body"])}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
