"""Turns, answers, votes, and phase changes."""

from __future__ import annotations

from services.supabase_client import get_backend
from utils.constants import ERR_ANSWER, ERR_VOTE, VERDICTS, clean_answer, fail


def start_game(token: str) -> dict:
    return get_backend().start_game(token)


def submit_answer(token: str, body: str) -> dict:
    cleaned, error = clean_answer(body)
    if error or not cleaned:
        return fail(error or ERR_ANSWER)
    return get_backend().submit_answer(token, cleaned)


def submit_vote(token: str, answer_id: str, verdict: str) -> dict:
    if verdict not in VERDICTS or not answer_id:
        return fail(ERR_VOTE)
    return get_backend().submit_vote(token, answer_id, verdict)


def sync_room(token: str) -> dict:
    return get_backend().sync_room(token)


def skip_phase(token: str) -> dict:
    return get_backend().skip_phase(token)


def next_round(token: str) -> dict:
    return get_backend().next_round(token)


def play_again(token: str) -> dict:
    return get_backend().play_again(token)


def end_game(token: str) -> dict:
    return get_backend().end_game(token)
