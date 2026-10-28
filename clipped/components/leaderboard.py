"""Round receipts and the final winner."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from components.shared import (
    esc,
    format_points,
    host_end,
    poll_view,
    primary,
    reconnecting,
    place_label,
    points_label,
    render_standings,
    spots_html,
    reveal_class,
    secondary,
    show_round_label,
)
from services import game_service
from utils.session import clear_seat


@st.fragment(run_every=timedelta(seconds=1.5))
def render_leaderboard() -> None:
    view = poll_view()
    if not view.get("ok"):
        reconnecting()
        return
    board = view.get("leaderboard") or {}
    show_round_label(board.get("round_number", 1), board.get("total_rounds", 1), board.get("category"))
    st.markdown('<p class="eyebrow">The receipts are in</p>', unsafe_allow_html=True)
    st.markdown(f'<h2 class="question">{esc(board.get("question"))}</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hint score-hint">Each ranking pays the spot it put this answer in. The total is the score.</p>',
        unsafe_allow_html=True,
    )
    reveals = board.get("reveals") or []
    if not reveals:
        st.markdown('<p class="hint">Nobody locked an answer in.</p>', unsafe_allow_html=True)
    for reveal in reveals:
        klass = reveal_class(reveal)
        st.markdown(
            f"""
            <div class="reveal {esc(klass)}">
              <div class="tile-top">
                <span class="verdict {esc(klass)}">{esc(place_label(reveal))}</span>
                <span class="tile-pay">{esc(points_label(reveal))}</span>
              </div>
              <p class="answer-body">{esc(reveal["body"])}</p>
              <p class="byline">{esc(reveal["author"])}</p>
              {spots_html(reveal)}
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown('<h2 class="section-title">Standings</h2>', unsafe_allow_html=True)
    render_standings(board.get("standings") or [], show_round=board.get("round_number", 1) > 1)
    if view["you"]["is_host"]:
        label = "Show the winner" if board.get("is_final_round") else "Next round"
        if primary(label, "next-round"):
            result = game_service.next_round(st.session_state["token"])
            if not result.get("ok"):
                st.error(result.get("error", "Couldn't move on."))
            else:
                st.rerun(scope="app")
        host_end(view)
    else:
        st.markdown('<p class="wait">Waiting for the host…</p>', unsafe_allow_html=True)


@st.fragment(run_every=timedelta(seconds=1.5))
def render_final() -> None:
    view = poll_view()
    if not view.get("ok"):
        reconnecting()
        return
    final = view.get("final") or {}
    winners = final.get("winners") or ["Nobody"]
    title = "It's a tie" if final.get("tied") else winners[0]
    points = 0
    if final.get("standings"):
        points = int(final["standings"][0]["points"])
    names = ", ".join(winners)
    st.markdown(
        f"""
        <div class="winner">
          <p class="eyebrow">Absolutely clipped.</p>
          <h2>{esc(title if not final.get("tied") else names)}</h2>
          <p class="score">{format_points(points)} points</p>
          <p class="hint">{'Shared the top.' if final.get("tied") else 'Takes the room.'}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<h2 class="section-title">Final rankings</h2>', unsafe_allow_html=True)
    render_standings(final.get("standings") or [])
    best = final.get("best_answer")
    best_html = "No answers this game."
    if best:
        best_html = f'{esc(best["body"])} — {esc(best["author"])}'
    st.markdown(
        f"""
        <div class="stat-grid">
          <div><div class="stat-label">Firsts</div><div class="stat-value">{int(final.get("firsts") or 0)}</div></div>
          <div><div class="stat-label">Answers</div><div class="stat-value">{int(final.get("total_answers") or 0)}</div></div>
          <div><div class="stat-label">Best line</div><div class="stat-value" style="font-size:1rem">{best_html}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if best:
        st.markdown(
            f'<div class="reveal gem"><p class="eyebrow">Best-rated answer</p><p class="answer-body">{esc(best["body"])}</p><p class="byline">{esc(best["author"])} · {format_points(best["points"])}</p></div>',
            unsafe_allow_html=True,
        )
    if view["you"]["is_host"]:
        if primary("Play again", "play-again"):
            result = game_service.play_again(st.session_state["token"])
            if not result.get("ok"):
                st.error(result.get("error", "Couldn't reset."))
            else:
                st.rerun(scope="app")
    else:
        st.markdown('<p class="wait">Waiting for the host…</p>', unsafe_allow_html=True)
    if secondary("New room", "new-room"):
        from services import room_service

        token = st.session_state.get("token")
        if token:
            room_service.leave_room(token)
        clear_seat()
        st.rerun(scope="app")
