"""Shared limits, copy, and light validation. No Streamlit imports."""

from __future__ import annotations

import re

PHASE_LOBBY = "lobby"
PHASE_PROMPT = "prompt"
PHASE_VOTING = "voting"
PHASE_LEADERBOARD = "leaderboard"
PHASE_FINAL = "final_results"
PHASE_EXPIRED = "expired"

PHASES = (
    PHASE_LOBBY,
    PHASE_PROMPT,
    PHASE_VOTING,
    PHASE_LEADERBOARD,
    PHASE_FINAL,
    PHASE_EXPIRED,
)

CATEGORY_ORDER = ("lore", "exposing", "deep_cuts", "brainrot", "legendary")

CATEGORY_LABELS = {
    "lore": "Friend group lore",
    "exposing": "Exposing the group",
    "deep_cuts": "Deep cuts",
    "brainrot": "Brainrot and chaos",
    "legendary": "Legendary moments",
    "custom": "Custom",
}

ROUND_OPTIONS = (5, 10, 15, 20)
TIMER_OPTIONS = (30, 45, 60, 90)
ORDER_OPTIONS = ("random", "sequential")

MIN_NAME = 2
MAX_NAME = 20
MIN_ANSWER = 1
MAX_ANSWER = 280
MIN_PROMPT = 10
MAX_PROMPT = 240
MAX_PLAYERS = 12
AWAY_SECONDS = 45
ROOM_TTL_HOURS = 12
MUTATION_GAP_MS = 300
MAX_IMPORT = 40

ERR_HOST = "Only the host can do that."
ERR_LOCKED = "Already locked in."
ERR_NAME = "That name's taken. Pick another."
ERR_EXPIRED = "This room expired."
ERR_MISSING = "That room doesn't exist."
ERR_STARTED = "This game already started."
ERR_FULL = "Room's full."
ERR_CODE = "Enter a four-digit code."
ERR_DISPLAY = "Use 2–20 characters."
ERR_NEED_PLAYERS = "Need at least two players."
ERR_NEED_QUESTIONS = "Not enough questions for that many rounds."
ERR_SLOW = "Slow down a second."
ERR_SESSION = "Session expired. Join again."
ERR_TIME = "Time's up."
ERR_VOTE = "That order doesn't count."
ERR_ANSWER = "Drop an answer first."
ERR_LONG_ANSWER = "Keep it under 280 characters."
ERR_PROMPT = "Questions need 10–240 characters."
ERR_SETTINGS = "Those settings don't work. Check rounds, timers, and categories."
ERR_MIDGAME = "You can't change that mid-game."
ERR_SKIP = "Nothing to skip."
ERR_FINISH = "Finish the game before playing again."
ERR_NOT_STARTED = "The game hasn't started."
ERR_CODE_SPACE = "Couldn't mint a room code. Try again."
ERR_GENERIC = "The server could not reach the game. Try again."
ERR_CATEGORY = "Pick a real category."

PHASE_TOAST = {
    PHASE_LOBBY: "The squad is assembling.",
    PHASE_PROMPT: "Cook something up.",
    PHASE_VOTING: "Put the best on top.",
    PHASE_LEADERBOARD: "The receipts are in.",
    PHASE_FINAL: "Absolutely clipped.",
}

LOCAL_BANNER = "This room lives on this server. Add Supabase before you share it publicly."

_CODE = re.compile(r"^\d{4}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_name(raw: str | None) -> str | None:
    name = " ".join((raw or "").split())
    if _CONTROL.search(name):
        return None
    if not MIN_NAME <= len(name) <= MAX_NAME:
        return None
    return name


def clean_code(raw: str | None) -> str | None:
    code = "".join((raw or "").split())
    if not _CODE.match(code):
        return None
    return code


def clean_answer(raw: str | None) -> tuple[str | None, str | None]:
    body = (raw or "").strip()
    if not body:
        return None, ERR_ANSWER
    if len(body) > MAX_ANSWER:
        return None, ERR_LONG_ANSWER
    if _CONTROL.search(body):
        return None, ERR_ANSWER
    return body, None


def clean_prompt(raw: str | None) -> str | None:
    body = " ".join((raw or "").split())
    if _CONTROL.search(body):
        return None
    if not MIN_PROMPT <= len(body) <= MAX_PROMPT:
        return None
    return body


def clean_categories(raw: list[str] | tuple[str, ...] | None) -> list[str] | None:
    if raw is None:
        return None
    seen: list[str] = []
    for item in raw:
        if item not in CATEGORY_ORDER:
            return None
        if item not in seen:
            seen.append(item)
    return seen


def fail(message: str) -> dict:
    return {"ok": False, "error": message}
