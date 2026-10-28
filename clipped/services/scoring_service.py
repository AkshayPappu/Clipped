"""Ranking scores.

Players submit an order, best to worst. They do not send points. Each ballot
awards Borda weight (first place gets one weight per answer, last place gets
1). The weights are summed into a consensus order, and that order is what
scores: best is 300, worst is 0, and the steps in between are even.

A tie takes the worse place in the tie, so a split room cannot inflate a
score. No ballots at all score 0. SQL `_place_points` and `_finalize_round`
use the same integer formula and must stay in lockstep with this module.
"""

from __future__ import annotations


def place_points(place: int, count: int) -> int:
    """Points for a 1-based consensus place. Best is 300, worst is 0."""
    if count <= 0 or place <= 0:
        return 0
    if count == 1:
        return 300
    span = count - 1
    return (300 * (count - place) + span // 2) // span


def score_ballots(answer_ids: list[str], ballots: list[list[str]]) -> list[dict]:
    """Score a round from complete best-to-worst ballots.

    Returns one row per answer, best consensus place first. `place` is the
    worse slot of a tie. `place` is 0 when nobody submitted a ranking.
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
            totals[answer_id] += count - index
    ordered = sorted(ids, key=lambda answer_id: (-totals[answer_id], answer_id))
    groups: list[list[str]] = []
    for answer_id in ordered:
        if not groups or totals[groups[-1][0]] != totals[answer_id]:
            groups.append([answer_id])
        else:
            groups[-1].append(answer_id)
    scored: list[dict] = []
    slot = 0
    for group in groups:
        slot += len(group)
        tied = len(group) > 1
        points = place_points(slot, count)
        for answer_id in group:
            scored.append(
                {
                    "answer_id": answer_id,
                    "place": slot,
                    "points": points,
                    "borda": totals[answer_id],
                    "tied": tied,
                }
            )
    return scored
