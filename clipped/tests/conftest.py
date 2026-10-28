from datetime import timedelta

import pytest

from services.memory_store import MemoryStore


@pytest.fixture
def store() -> MemoryStore:
    game = MemoryStore()
    game.mutation_gap = timedelta(0)
    return game
