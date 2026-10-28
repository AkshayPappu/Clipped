"""Ranking scores.

Players submit an order, best to worst. They do not send a total. Each spot
on a ranking pays the answer in that spot: first place pays 300, last place
pays 0, and the spots between are even steps. An answer's score is the sum of
what every ranking paid it. The highest total finishes first.

A tie keeps the points both answers earned. No rankings at all score 0.
SQL `_place_points` and `_finalize_round` use the same formula.
"""

from __future__ import annotations


def place_points(place: int, count: int) -> int:
    """What one ranking pays the answer in a 1-based spot. First is 300, last is 0."""
    if count <= 0 or place <= 0:
        return 0
    if count == 1:
        return 300
    span = count - 1
    return (300 * (count - place) + span // 2) // span


def score_ballots(answer_ids: list[str], ballots: list[list[str]]) -> list[dict]:
    """Score a round by adding up every ranking.

    Returns one row per answer, highest total first. `place` is 1 for the
    leader, and tied answers share that place. `place` is 0 when nobody
    submitted a ranking.
    """
    ids = list(answer_ids)
    if not ids:
        return []
    expected = set(ids)
    if len(expected) != len(ids):
        raise ValueError("answer ids must be unique")
    totals = {answer_id: 0 for answer_id in ids}
    valid: list[list[str]] = []
    for ballot in ballots:
        if len(ballot) != len(ids) or set(ballot) != expected:
            raise ValueError("ballot must rank every answer once")
        valid.append(list(ballot))
    if not valid:
        return [
            {"answer_id": answer_id, "place": 0, "points": 0, "borda": 0, "tied": False}
            for answer_id in ids
        ]
    count = len(ids)
    for ballot in valid:
        for index, answer_id in enumerate(ballot):
            totals[answer_id] += place_points(index + 1, count)
    ordered = sorted(ids, key=lambda answer_id: (-totals[answer_id], answer_id))
    groups: list[list[str]] = []
    for answer_id in ordered:
        if not groups or totals[groups[-1][0]] != totals[answer_id]:
            groups.append([answer_id])
        else:
            groups[-1].append(answer_id)
    scored: list[dict] = []
    next_place = 1
    for group in groups:
        place = next_place
        next_place += len(group)
        tied = len(group) > 1
        for answer_id in group:
            scored.append(
                {
                    "answer_id": answer_id,
                    "place": place,
                    "points": totals[answer_id],
                    "borda": totals[answer_id],
                    "tied": tied,
                }
            )
    return scored
