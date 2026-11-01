"""Scoring for M2, fixed by Amendment 4. Each estimate passes through a lock before it exists."""

from datetime import date
from typing import Literal

import numpy as np
from scipy.optimize import minimize

from atlas.config import M2_ALPHA, M2_AMENDMENT_APPROVED, M2_FREEZE_DATE, M2_SUPPORT_P

Claim = Literal["supported", "suggestive", "null"]


class EventStudyLockedError(RuntimeError):
    """A number computed too early cannot be unseen, so this stops it being computed at all."""


def require_unlocked(
    today: date, approved: bool = M2_AMENDMENT_APPROVED, freeze: date = M2_FREEZE_DATE
) -> None:
    if not approved:
        raise EventStudyLockedError("Amendment 4 has not been approved.")
    if today < freeze:
        raise EventStudyLockedError(f"The M2 freeze date is {freeze.isoformat()}.")


def rank_p(estimate: float, null: np.ndarray) -> float:
    return float((1 + np.sum(null >= estimate)) / (1 + len(null)))


def placebo_interval(estimate: float, null: np.ndarray) -> tuple[float, float]:
    """Inverts the placebo test: steps the null could not rule out at the 90% level."""
    return estimate - float(np.quantile(null, 0.95)), estimate - float(np.quantile(null, 0.05))


def holm(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    highest = 0.0
    for position, (name, value) in enumerate(ordered):
        highest = max(highest, min(1.0, value * (len(ordered) - position)))
        adjusted[name] = highest
    return adjusted


def synthetic_weights(target: np.ndarray, donors: np.ndarray) -> np.ndarray:
    """Target has one value per day, donors one row per day and one column per grid."""
    count = donors.shape[1]
    result = minimize(
        lambda weights: float(np.mean((target - donors @ weights) ** 2)),
        np.full(count, 1 / count),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * count,
        constraints={"type": "eq", "fun": lambda weights: float(np.sum(weights) - 1)},
        options={"maxiter": 500, "ftol": 1e-10},
    )
    if not result.success:
        raise ValueError(f"Synthetic control did not converge: {result.message}")
    return np.asarray(result.x, dtype=float)


def synthetic_gap(
    target_pre: np.ndarray,
    donors_pre: np.ndarray,
    target_post: np.ndarray,
    donors_post: np.ndarray,
) -> float:
    weights = synthetic_weights(target_pre, donors_pre)
    pre_gap = target_pre - donors_pre @ weights
    post_gap = target_post - donors_post @ weights
    return float(post_gap.mean() - pre_gap.mean())


def claim(
    adjusted_p: float,
    estimate: float,
    lead_estimate: float,
    threshold: float,
    other_grid_p: float,
    synthetic_gap_value: float,
) -> Claim:
    if adjusted_p >= M2_ALPHA:
        return "null"
    checks = (
        estimate > 0,
        lead_estimate <= threshold,
        other_grid_p <= M2_SUPPORT_P,
        synthetic_gap_value > 0,
    )
    return "supported" if all(checks) else "suggestive"
