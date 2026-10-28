"""Consensus scoring.

The category with the most votes wins. Ties break toward the lower point
value so a split room cannot inflate a score. Zero eligible votes score 0
and are not labeled fake news. SQL function `_consensus` implements the same
rule and must stay in lockstep with this module.
"""

from __future__ import annotations

from utils.constants import POINTS, VERDICT_COMMON, VERDICT_FAKE, VERDICT_GEM, VERDICT_NONE


def consensus(gem: int, common: int, fake: int) -> tuple[str, int]:
    if gem < 0 or common < 0 or fake < 0:
        raise ValueError("vote counts must be non-negative")
    if gem + common + fake == 0:
        return VERDICT_NONE, 0
    best = max(gem, common, fake)
    # Check low point values first so ties lose on purpose.
    if fake == best:
        return VERDICT_FAKE, POINTS[VERDICT_FAKE]
    if common == best:
        return VERDICT_COMMON, POINTS[VERDICT_COMMON]
    return VERDICT_GEM, POINTS[VERDICT_GEM]
