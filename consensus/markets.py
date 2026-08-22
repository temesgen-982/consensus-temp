from __future__ import annotations


def derive_from_score(hg: int, ag: int) -> dict[str, str]:
    """Market picks implied by a predicted final score."""
    return {
        "1x2": "1" if hg > ag else ("2" if ag > hg else "X"),
        "btts": "Yes" if hg > 0 and ag > 0 else "No",
        "over_under": "Over" if hg + ag >= 3 else "Under",
    }
