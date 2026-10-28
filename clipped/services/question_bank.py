"""Load builtin prompts from database/seed.sql so local games use the real bank."""

from __future__ import annotations

import re
import uuid
from functools import lru_cache
from pathlib import Path

NAMESPACE = uuid.UUID("8f3a1c2e-6b7d-4e9a-9c11-0a1b2c3d4e5f")
SEED_PATH = Path(__file__).resolve().parents[1] / "database" / "seed.sql"
_ROW = re.compile(r"\('([a-z_]+)', '((?:[^']|'')*)', true, (\d+)\)")


def load_builtin_prompts(path: Path | None = None) -> list[tuple[str, str, str, int]]:
    """Return (id, category, body, sort_index) in file order."""
    if path is None:
        return _load_default_bank()
    return _parse_bank(path)


@lru_cache(maxsize=1)
def _load_default_bank() -> list[tuple[str, str, str, int]]:
    return _parse_bank(SEED_PATH)


def _parse_bank(path: Path) -> list[tuple[str, str, str, int]]:
    text = path.read_text(encoding="utf-8")
    rows: list[tuple[str, str, str, int]] = []
    seen: set[str] = set()
    for category, raw_body, index in _ROW.findall(text):
        body = raw_body.replace("''", "'")
        if body in seen:
            continue
        seen.add(body)
        prompt_id = str(uuid.uuid5(NAMESPACE, f"{category}:{body}"))
        rows.append((prompt_id, category, body, int(index)))
    if len(rows) < 100:
        raise RuntimeError(f"Question bank is too small ({len(rows)}). Check seed.sql.")
    return rows
