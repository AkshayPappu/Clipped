"""Supabase service-role client and backend selection.

The service role key stays on the Streamlit server. Browsers never see it.
When credentials are missing, the app uses the in-memory store so a local
party still runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from services.memory_store import MemoryStore
from utils.constants import ERR_GENERIC, fail

_backend = None


def get_backend():
    global _backend
    if _backend is None:
        _backend = build_backend()
    return _backend


def set_backend(backend) -> None:
    global _backend
    _backend = backend


def build_backend():
    _load_env()
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not _usable(url, key):
        secret_url, secret_key = _from_streamlit_secrets()
        url = url or secret_url
        key = key or secret_key
    if _usable(url, key):
        return SupabaseBackend(url, key)
    return MemoryStore()


def _usable(url: str, key: str) -> bool:
    if not url or not key:
        return False
    lowered = f"{url} {key}".lower()
    if "your-project" in lowered or "your-service-role" in lowered:
        return False
    return True


def _from_streamlit_secrets() -> tuple[str, str]:
    try:
        import streamlit as st

        url = str(st.secrets.get("SUPABASE_URL", "")).strip()
        key = str(st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")).strip()
        return url, key
    except Exception:
        return "", ""


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    load_dotenv(root / "clipped" / ".env")


class SupabaseBackend:
    """RPC-only access. No direct table reads, so early answers cannot leak."""

    local_mode = False

    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client

        self.client = create_client(url, key)

    def _rpc(self, name: str, params: dict) -> dict:
        try:
            response = self.client.rpc(name, params).execute()
        except Exception:
            return fail(ERR_GENERIC)
        data = response.data
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return fail(ERR_GENERIC)
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            return fail(ERR_GENERIC)
        return data

    def create_room(self, display_name: str) -> dict:
        return self._rpc("create_room", {"p_display_name": display_name})

    def join_room(self, code: str, display_name: str) -> dict:
        return self._rpc("join_room", {"p_code": code, "p_display_name": display_name})

    def reconnect(self, token: str) -> dict:
        return self._rpc("reconnect", {"p_token": token})

    def leave_room(self, token: str) -> dict:
        return self._rpc("leave_room", {"p_token": token})

    def update_settings(
        self,
        token: str,
        total_rounds: int,
        answer_seconds: int,
        vote_seconds: int,
        categories: list[str],
        question_order: str,
    ) -> dict:
        return self._rpc(
            "update_settings",
            {
                "p_token": token,
                "p_total_rounds": total_rounds,
                "p_answer_seconds": answer_seconds,
                "p_vote_seconds": vote_seconds,
                "p_categories": categories,
                "p_question_order": question_order,
            },
        )

    def save_custom_prompt(self, token: str, body: str, prompt_id: str | None = None) -> dict:
        return self._rpc(
            "save_custom_prompt",
            {"p_token": token, "p_body": body, "p_prompt_id": prompt_id},
        )

    def delete_custom_prompt(self, token: str, prompt_id: str) -> dict:
        return self._rpc("delete_custom_prompt", {"p_token": token, "p_prompt_id": prompt_id})

    def set_prompt_included(self, token: str, prompt_id: str, included: bool) -> dict:
        return self._rpc(
            "set_prompt_included",
            {"p_token": token, "p_prompt_id": prompt_id, "p_included": included},
        )

    def import_prompts(self, token: str, raw_text: str) -> dict:
        return self._rpc("import_prompts", {"p_token": token, "p_raw": raw_text})

    def start_game(self, token: str) -> dict:
        return self._rpc("start_game", {"p_token": token})

    def submit_answer(self, token: str, body: str) -> dict:
        return self._rpc("submit_answer", {"p_token": token, "p_body": body})

    def submit_ranking(self, token: str, answer_ids: list[str]) -> dict:
        return self._rpc(
            "submit_ranking",
            {"p_token": token, "p_order": answer_ids},
        )

    def sync_room(self, token: str) -> dict:
        return self._rpc("sync_room", {"p_token": token})

    def skip_phase(self, token: str) -> dict:
        return self._rpc("skip_phase", {"p_token": token})

    def next_round(self, token: str) -> dict:
        return self._rpc("next_round", {"p_token": token})

    def play_again(self, token: str) -> dict:
        return self._rpc("play_again", {"p_token": token})

    def end_game(self, token: str) -> dict:
        return self._rpc("end_game", {"p_token": token})
