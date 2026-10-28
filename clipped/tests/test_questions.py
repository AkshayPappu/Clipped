from collections import Counter

from services.question_bank import load_builtin_prompts
from utils.constants import CATEGORY_ORDER, MAX_PROMPT, MIN_PROMPT


def test_bank_covers_every_pack():
    rows = load_builtin_prompts()
    counts = Counter(category for _id, category, _body, _index in rows)
    assert len(rows) >= 110
    for category in CATEGORY_ORDER:
        assert counts[category] >= 22
    bodies = [body for _id, _category, body, _index in rows]
    assert len(bodies) == len(set(bodies))
    assert all(MIN_PROMPT <= len(body) <= MAX_PROMPT for body in bodies)
