import pytest

from services.scoring_service import consensus
from utils.constants import POINTS


def test_gem_wins_outright():
    assert consensus(3, 1, 0) == ("gem", POINTS["gem"])


def test_common_wins_outright():
    assert consensus(1, 4, 2) == ("common", POINTS["common"])


def test_fake_wins_outright():
    assert consensus(0, 1, 3) == ("fake", 0)


def test_tie_gem_and_common_scores_lower():
    assert consensus(2, 2, 0) == ("common", 100)


def test_tie_gem_and_fake_scores_lower():
    assert consensus(2, 0, 2) == ("fake", 0)


def test_tie_common_and_fake_scores_lower():
    assert consensus(0, 3, 3) == ("fake", 0)


def test_three_way_tie_scores_zero():
    assert consensus(1, 1, 1) == ("fake", 0)


def test_zero_votes_are_unrated():
    assert consensus(0, 0, 0) == ("none", 0)


def test_negative_counts_rejected():
    with pytest.raises(ValueError):
        consensus(-1, 0, 0)
