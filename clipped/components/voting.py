"""Anonymous voting. Cards are stacked for phones."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from components.shared import (
    esc,
    host_end,
    host_skip,
    poll_view,
    reconnecting,
    render_progress,
    render_timer,
    show_round_label,
)
from services import game_service
from utils.constants import VERDICT_COMMON, VERDICT_FAKE, VERDICT_GEM, VERDICT_LABEL


@st.fragment(run_every=timedelta(seconds=1.5))
def render_voting() -> None:
    view = poll_view()
    if not view.get("ok"):
        reconnecting()
        return
    voting = view.get("voting") or {}
    show_round_label(voting.get("round_number", 1), voting.get("total_rounds", 1), voting.get("category"))
    st.markdown(f'<h2 class="question">{esc(voting.get("question"))}</h2>', unsafe_allow_html=True)
    st.markdown('<p class="eyebrow">Time to judge</p>', unsafe_allow_html=True)
    render_timer(view.get("server_now"), voting.get("deadline"), view["room"]["vote_seconds"])
    render_progress(
        int(voting.get("votes_cast") or 0),
        int(voting.get("votes_needed") or 0),
        "votes in",
    )
    for answer in voting.get("answers") or []:
        _card(answer)
    if not voting.get("answers"):
        st.markdown('<p class="hint">No answers landed. Brutal.</p>', unsafe_allow_html=True)
    host_skip(view)
    host_end(view)


def _card(answer: dict) -> None:
    st.markdown(
        f"""
        <div class="answer-card">
          <p class="eyebrow">Someone really said…</p>
          <p class="answer-body">{esc(answer["body"])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if answer.get("is_own"):
        st.markdown('<p class="hint">This one\'s yours. Sit this out.</p>', unsafe_allow_html=True)
        return
    if answer.get("your_vote"):
        label = VERDICT_LABEL.get(answer["your_vote"], answer["your_vote"])
        st.markdown(f'<p class="hint">You called it · {esc(label)}</p>', unsafe_allow_html=True)
        return
    if st.button("Gem · 300", key=f"gem-{answer['id']}", width="stretch"):
        _cast(answer["id"], VERDICT_GEM)
    if st.button("Common · 100", key=f"common-{answer['id']}", width="stretch"):
        _cast(answer["id"], VERDICT_COMMON)
    if st.button("Fake news · 0", key=f"fake-{answer['id']}", width="stretch"):
        _cast(answer["id"], VERDICT_FAKE)


def _cast(answer_id: str, verdict: str) -> None:
    result = game_service.submit_vote(st.session_state["token"], answer_id, verdict)
    if not result.get("ok"):
        st.error(result.get("error", "Couldn't save that vote."))
        return
    st.rerun()
