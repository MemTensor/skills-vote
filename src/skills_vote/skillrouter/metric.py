from __future__ import annotations

import numpy as np


def hit_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    return 1.0 if any(skill_id in relevant_ids for skill_id in ranked_ids[:k]) else 0.0


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k_ids = set(ranked_ids[:k])
    return float(np.mean([skill_id in top_k_ids for skill_id in relevant_ids]))


def full_coverage_at_k(ranked_ids: list[str], required_ids: set[str], k: int) -> float:
    if not required_ids:
        return 1.0
    return 1.0 if required_ids.issubset(set(ranked_ids[:k])) else 0.0
