import pytest

from services.scoring_service import place_points, score_ballots


def test_place_points_scale_from_best_to_worst():
    assert place_points(1, 1) == 300
    assert [place_points(place, 2) for place in (1, 2)] == [300, 0]
    assert [place_points(place, 3) for place in (1, 2, 3)] == [300, 150, 0]
    assert [place_points(place, 4) for place in (1, 2, 3, 4)] == [300, 200, 100, 0]


def test_agreed_order_adds_every_first_place_vote():
    scored = score_ballots(["a", "b"], [["a", "b"], ["a", "b"]])
    assert [(row["answer_id"], row["place"], row["points"], row["tied"]) for row in scored] == [
        ("a", 1, 600, False),
        ("b", 2, 0, False),
    ]


def test_split_order_keeps_both_totals():
    scored = score_ballots(["a", "b"], [["a", "b"], ["b", "a"]])
    assert {row["answer_id"]: row["points"] for row in scored} == {"a": 300, "b": 300}
    assert all(row["tied"] and row["place"] == 1 for row in scored)


def test_three_rankings_add_the_middle_spot():
    ballots = [["a", "b", "c"], ["a", "b", "c"], ["a", "b", "c"]]
    scored = {row["answer_id"]: row for row in score_ballots(["a", "b", "c"], ballots)}
    assert (scored["a"]["points"], scored["b"]["points"], scored["c"]["points"]) == (900, 450, 0)


def test_tied_leaders_share_first_and_keep_their_points():
    ballots = [["a", "b", "c"], ["b", "a", "c"]]
    scored = {row["answer_id"]: row for row in score_ballots(["a", "b", "c"], ballots)}
    assert scored["a"]["points"] == 450
    assert scored["b"]["points"] == 450
    assert scored["a"]["place"] == 1 and scored["b"]["place"] == 1
    assert scored["a"]["tied"] and scored["b"]["tied"]
    assert scored["c"]["points"] == 0
    assert scored["c"]["place"] == 3
    assert not scored["c"]["tied"]


def test_no_ballots_score_nothing():
    scored = score_ballots(["a", "b"], [])
    assert all(row["points"] == 0 and row["place"] == 0 and not row["tied"] for row in scored)


def test_ballot_must_rank_every_answer():
    with pytest.raises(ValueError):
        score_ballots(["a", "b"], [["a"]])
