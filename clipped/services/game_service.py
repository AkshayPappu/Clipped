"""Turns, answers, rankings, and phase changes."""

from __future__ import annotations

from services.supabase_client import get_backend
from utils.constants import ERR_ANSWER, ERR_VOTE, clean_answer, fail


def start_game(token: str) -> dict:
    return get_backend().start_game(token)


def submit_answer(token: str, body: str) -> dict:
    cleaned, error = clean_answer(body)
    if error or not cleaned:
        return fail(error or ERR_ANSWER)
    return get_backend().submit_answer(token, cleaned)


def submit_ranking(token: str, answer_ids: list[str]) -> dict:
    if not answer_ids or len(answer_ids) != len(set(answer_ids)):
        return fail(ERR_VOTE)
    return get_backend().submit_ranking(token, list(answer_ids))


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
