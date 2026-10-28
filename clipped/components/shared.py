"""Visual primitives shared across every phase."""

from __future__ import annotations

import hashlib
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from services import game_service
from utils.constants import CATEGORY_LABELS, LOCAL_BANNER

_CSS = Path(__file__).resolve().parents[1] / "styles" / "theme.css"


def inject_css() -> None:
    css = _CSS.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def wordmark(compact: bool = False) -> None:
    klass = "brand compact" if compact else "brand"
    tagline = "" if compact else '<p class="tagline">Only the real ones know.</p>'
    st.markdown(
        f'<div class="{klass}"><div class="wordmark">clipped<span>.</span></div>{tagline}</div>',
        unsafe_allow_html=True,
    )


def local_banner(view: dict) -> None:
    if view.get("local_mode"):
        st.markdown(f'<p class="local-banner">{html.escape(LOCAL_BANNER)}</p>', unsafe_allow_html=True)


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def format_points(value: int) -> str:
    return f"{int(value):,}"


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def seconds_left(server_now: str | None, deadline: str | None) -> int:
    end = parse_iso(deadline)
    now = parse_iso(server_now)
    if not end or not now:
        return 0
    return max(0, math.ceil((end - now).total_seconds() - 1e-6))


def clock(seconds: int) -> str:
    minutes, secs = divmod(max(0, seconds), 60)
    return f"{minutes}:{secs:02d}"


def primary(label: str, key: str) -> bool:
    return st.button(label, key=key, type="primary", width="stretch")


def secondary(label: str, key: str) -> bool:
    return st.button(label, key=key, type="secondary", width="stretch")


def copy_row(items: list[tuple[str, str]]) -> None:
    buttons = []
    binders = []
    for label, text in items:
        digest = hashlib.sha256(f"{label}:{text}".encode("utf-8")).hexdigest()[:12]
        element_id = f"copy-{digest}"
        buttons.append(f'<button id="{element_id}" type="button">{html.escape(label)}</button>')
        binders.append(
            f"""
            const btn_{digest} = document.getElementById("{element_id}");
            if (btn_{digest} && !btn_{digest}.dataset.bound) {{
              btn_{digest}.dataset.bound = "1";
              btn_{digest}.addEventListener("click", async () => {{
                const value = {json.dumps(text)};
                try {{
                  await navigator.clipboard.writeText(value);
                }} catch (err) {{
                  const area = document.createElement("textarea");
                  area.value = value;
                  document.body.appendChild(area);
                  area.select();
                  document.execCommand("copy");
                  area.remove();
                }}
                btn_{digest}.textContent = "Copied";
                setTimeout(() => {{ btn_{digest}.textContent = {json.dumps(label)}; }}, 1200);
              }});
            }}
            """
        )
    st.html(
        f"""
        <style>
          .copy-row {{ display: flex; gap: 8px; margin: 2px 0 0; }}
          .copy-row button {{
            flex: 1;
            min-height: 40px;
            border: 0;
            border-radius: 999px;
            appearance: none;
            background-color: transparent;
            color: #c9c9d2;
            font: 600 15px "Outfit", system-ui, sans-serif;
            letter-spacing: -0.02em;
            cursor: pointer;
          }}
          .copy-row button:hover {{ color: white; }}
        </style>
        <div class="copy-row">{"".join(buttons)}</div>
        <script>
          {" ".join(binders)}
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def poll_view() -> dict:
    """Refresh from the server. A phase change reruns the whole app."""
    view = game_service.sync_room(st.session_state["token"])
    if not view.get("ok"):
        return view
    key = f"{view['room']['status']}:{view['room']['current_round']}"
    if key != st.session_state.get("phase_key"):
        st.rerun(scope="app")
    return view


def render_timer(server_now: str | None, deadline: str | None, total: int) -> None:
    remaining = seconds_left(server_now, deadline)
    ratio = 0 if total <= 0 else min(1, remaining / total)
    low = " low" if remaining <= 10 else ""
    st.markdown(
        f"""
        <div class="timer-wrap">
          <div class="timer-row"><span class="eyebrow">Time left</span><span class="timer-num">{clock(remaining)}</span></div>
          <div class="timer-track"><div class="timer-fill{low}" style="width:{ratio * 100:.1f}%"></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_progress(done: int, total: int, label: str) -> None:
    st.markdown(
        f'<p class="hint"><strong style="color:white">{done}/{total}</strong> {esc(label)}</p>',
        unsafe_allow_html=True,
    )


def render_players(view: dict) -> None:
    you = view["you"]["id"]
    count = view["room"]["player_count"]
    st.markdown(
        f'<h2 class="section-title">The squad <span class="count-pill">{count}</span></h2>',
        unsafe_allow_html=True,
    )
    cards = []
    for person in view["players"]:
        initial = esc(person["display_name"][:1].upper())
        name = esc(person["display_name"])
        classes = ["player-card"]
        badges = []
        if person["is_host"]:
            classes.append("host")
            badges.append('<span class="badge host">HOST</span>')
        if person["id"] == you:
            badges.append('<span class="badge you">YOU</span>')
        if person.get("is_away"):
            classes.append("away")
            badges.append('<span class="badge away">AWAY</span>')
        cards.append(
            f'<div class="{" ".join(classes)}"><div class="avatar">{initial}</div>'
            f'<div class="player-name">{name}</div>{"".join(badges)}</div>'
        )
    st.markdown("".join(cards), unsafe_allow_html=True)


def category_label(key: str | None) -> str:
    if not key:
        return ""
    return CATEGORY_LABELS.get(key, key)


def ordinal(place: int) -> str:
    if 10 <= place % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(place % 10, "th")
    return f"{place}{suffix}"


def spots_html(reveal: dict) -> str:
    spots = reveal.get("spots") or []
    counts = [int(count or 0) for count in spots]
    if not counts or not any(counts):
        return ""
    pills = []
    for index, count in enumerate(counts):
        quiet = " quiet" if count == 0 else ""
        pills.append(
            f'<span class="spot{quiet}"><span class="spot-place">{esc(ordinal(index + 1))}</span>'
            f'<span class="spot-count">{count}</span></span>'
        )
    return f'<div class="spots" aria-label="Votes by spot">{"".join(pills)}</div>'


def place_label(reveal: dict) -> str:
    place = int(reveal.get("place") or 0)
    if place <= 0:
        return "No rankings"
    if reveal.get("tied"):
        return f"Tied · {ordinal(place)}"
    return ordinal(place)


def points_label(reveal: dict) -> str:
    points = int(reveal.get("points") or 0)
    return f"+{format_points(points)}" if points else "+0"


def reveal_class(reveal: dict) -> str:
    place = int(reveal.get("place") or 0)
    if place == 1 and not reveal.get("tied"):
        return "gem"
    if reveal.get("tied"):
        return "common"
    if place <= 0:
        return "none"
    return "lower"


def host_skip(view: dict) -> None:
    if not view["you"]["is_host"]:
        return
    if view["room"]["status"] not in ("prompt", "voting"):
        return
    if secondary("End phase early", "skip-phase"):
        result = game_service.skip_phase(st.session_state["token"])
        if not result.get("ok"):
            st.error(result.get("error", "Couldn't skip that."))
        else:
            st.rerun(scope="app")


def host_end(view: dict) -> None:
    if not view["you"]["is_host"]:
        return
    if view["room"]["status"] in ("lobby", "final_results", "expired"):
        return
    if st.session_state.get("confirm_end"):
        st.markdown('<p class="hint">End the game for everyone?</p>', unsafe_allow_html=True)
        if primary("Yes, end it", "end-yes"):
            result = game_service.end_game(st.session_state["token"])
            st.session_state["confirm_end"] = False
            if not result.get("ok"):
                st.error(result.get("error", "Couldn't end the game."))
            else:
                st.rerun(scope="app")
        if secondary("Never mind", "end-no"):
            st.session_state["confirm_end"] = False
            st.rerun()
        return
    if secondary("End game", "end-game"):
        st.session_state["confirm_end"] = True
        st.rerun()


def leave_button(key: str = "leave-room") -> None:
    if secondary("Leave room", key):
        game_service_leave()


def game_service_leave() -> None:
    from services import room_service
    from utils.session import clear_seat

    token = st.session_state.get("token")
    if token:
        room_service.leave_room(token)
    clear_seat()
    st.rerun(scope="app")


def render_standings(rows: list[dict], show_round: bool = False) -> None:
    blocks = []
    for row in rows:
        medal = {1: "1", 2: "2", 3: "3"}.get(row["rank"], str(row["rank"]))
        top = " top" if row["rank"] == 1 else ""
        delta = int(row.get("delta") or 0)
        delta_html = ""
        if show_round and delta:
            klass = "delta" if delta > 0 else "delta down"
            arrow = "▲" if delta > 0 else "▼"
            delta_html = f'<span class="{klass}">{arrow}{abs(delta)}</span>'
        round_bit = ""
        if show_round and int(row.get("round_points") or 0):
            round_bit = f' <span class="hint">+{format_points(row["round_points"])}</span>'
        blocks.append(
            f'<div class="standing{top}"><div class="rank">{medal}</div>'
            f'<div><div class="who">{esc(row["display_name"])}{delta_html}</div></div>'
            f'<div class="pts">{format_points(row["points"])}{round_bit}</div></div>'
        )
    st.markdown("".join(blocks) or '<p class="hint">No scores yet.</p>', unsafe_allow_html=True)


def reconnecting() -> None:
    st.markdown('<p class="reconnect">Reconnecting…</p>', unsafe_allow_html=True)


def show_round_label(number: int, total: int, category: str | None = None) -> None:
    cat = category_label(category)
    extra = f" · {esc(cat)}" if cat and cat != "Custom" else ""
    if category == "custom":
        extra = " · Custom"
    st.markdown(
        f'<p class="eyebrow">Round {number} / {total}{extra}</p>',
        unsafe_allow_html=True,
    )
