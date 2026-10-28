"""Room membership and host setup. The backend is the authority."""

from __future__ import annotations

from services.supabase_client import get_backend
from utils.constants import (
    ERR_CATEGORY,
    ERR_CODE,
    ERR_DISPLAY,
    ERR_PROMPT,
    ERR_SETTINGS,
    ORDER_OPTIONS,
    ROUND_OPTIONS,
    TIMER_OPTIONS,
    clean_categories,
    clean_code,
    clean_name,
    clean_prompt,
    fail,
)


def create_room(display_name: str) -> dict:
    name = clean_name(display_name)
    if not name:
        return fail(ERR_DISPLAY)
    return get_backend().create_room(name)


def join_room(code: str, display_name: str) -> dict:
    name = clean_name(display_name)
    if not name:
        return fail(ERR_DISPLAY)
    cleaned = clean_code(code)
    if not cleaned:
        return fail(ERR_CODE)
    return get_backend().join_room(cleaned, name)


def reconnect(token: str) -> dict:
    return get_backend().reconnect(token)


def leave_room(token: str) -> dict:
    return get_backend().leave_room(token)


def update_settings(
    token: str,
    total_rounds: int,
    answer_seconds: int,
    vote_seconds: int,
    categories: list[str],
    question_order: str,
) -> dict:
    cats = clean_categories(categories)
    if cats is None:
        return fail(ERR_CATEGORY)
    if (
        total_rounds not in ROUND_OPTIONS
        or answer_seconds not in TIMER_OPTIONS
        or vote_seconds not in TIMER_OPTIONS
        or question_order not in ORDER_OPTIONS
    ):
        return fail(ERR_SETTINGS)
    return get_backend().update_settings(
        token, total_rounds, answer_seconds, vote_seconds, cats, question_order
    )


def save_custom_prompt(token: str, body: str, prompt_id: str | None = None) -> dict:
    cleaned = clean_prompt(body)
    if not cleaned:
        return fail(ERR_PROMPT)
    return get_backend().save_custom_prompt(token, cleaned, prompt_id)


def delete_custom_prompt(token: str, prompt_id: str) -> dict:
    return get_backend().delete_custom_prompt(token, prompt_id)


def set_prompt_included(token: str, prompt_id: str, included: bool) -> dict:
    return get_backend().set_prompt_included(token, prompt_id, included)


def import_prompts(token: str, raw_text: str) -> dict:
    return get_backend().import_prompts(token, raw_text)
