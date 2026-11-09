"""Reciprocal Rank Fusion (Cormack et al., 2009).

score(d) = sum over rankings r of 1 / (k + rank_r(d)), with 1-based ranks.
Only ranks are used, so dense cosine similarities and BM25 scores (which are
on incomparable scales) never need to be normalised against each other.
"""

from collections.abc import Hashable, Sequence


def reciprocal_rank_fusion(rankings: Sequence[Sequence[Hashable]], k: int = 60) -> list[tuple[Hashable, float]]:
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[Hashable, float] = {}
    first_seen: dict[Hashable, int] = {}
    order = 0
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in first_seen:
                first_seen[key] = order
                order += 1
    # Ties are broken by first appearance, which keeps results deterministic.
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
