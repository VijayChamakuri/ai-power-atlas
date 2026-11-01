"""Scoring for M2, fixed by Amendment 4. Each estimate passes through a lock before it exists."""

from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from atlas.config import (
    BA_NAMES,
    M2_ALPHA,
    M2_AMENDMENT_APPROVED,
    M2_EARLY_APPROVED,
    M2_EARLY_FREEZE_DATE,
    M2_EARLY_PASS_P,
    M2_EARLY_SITE,
    M2_FREEZE_DATE,
    M2_SUPPORT_P,
    PEAK_WINDOW_DAYS,
    POST_DAYS,
    TRAIN_GAP_DAYS,
)
from atlas.ml.baseline import fit_predict
from atlas.ml.candidates import clean_demand
from atlas.ml.detectability import daily_residuals, null_threshold, step_estimate

Claim = Literal["supported", "suggestive", "null"]
EarlyReading = Literal["passes the main test", "pending Meta Kuna", "null"]


class EventStudyLockedError(RuntimeError):
    """A number computed too early cannot be unseen, so this stops it being computed at all."""


def require_unlocked(
    today: date, approved: bool = M2_AMENDMENT_APPROVED, freeze: date = M2_FREEZE_DATE
) -> None:
    if not approved:
        raise EventStudyLockedError("Amendment 4 has not been approved.")
    if today < freeze:
        raise EventStudyLockedError(f"The M2 freeze date is {freeze.isoformat()}.")


def require_early_unlocked(
    site: str,
    today: date,
    approved: bool = M2_EARLY_APPROVED,
    freeze: date = M2_EARLY_FREEZE_DATE,
) -> None:
    """Amendment 5 opens one site only. Everything else still waits for require_unlocked."""
    if not approved:
        raise EventStudyLockedError("Amendment 5 has not been approved.")
    if site != M2_EARLY_SITE:
        raise EventStudyLockedError(f"Amendment 5 covers only {M2_EARLY_SITE}.")
    if today < freeze:
        raise EventStudyLockedError(f"The early freeze date is {freeze.isoformat()}.")


def require_first_run(already_run: bool) -> None:
    if already_run:
        raise EventStudyLockedError("Amendment 5 allows one early run, and it has happened.")


def early_reading(p: float) -> EarlyReading:
    if p < M2_EARLY_PASS_P:
        return "passes the main test"
    return "pending Meta Kuna" if p < M2_ALPHA else "null"


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


def daily_errors(demand: pd.Series, features: pd.DataFrame, t: date) -> pd.Series:
    """Same model and windows as M1, so the M1 null windows still describe this estimate's noise."""
    cleaned = clean_demand(demand.dropna()).rename("demand")
    frame = features.join(cleaned, how="inner").dropna()
    moment = pd.Timestamp(t, tz="UTC")
    train_end = moment - pd.Timedelta(days=TRAIN_GAP_DAYS)
    window_end = moment + pd.Timedelta(days=POST_DAYS)
    future = frame[(frame.index >= train_end) & (frame.index < window_end)]
    return daily_residuals(future["demand"], fit_predict(frame[frame.index < train_end], future))


def peak_of(demand: pd.Series, freeze: date) -> float:
    cleaned = clean_demand(demand.dropna())
    start = pd.Timestamp(freeze - timedelta(days=PEAK_WINDOW_DAYS), tz="UTC")
    return float(cleaned[cleaned.index >= start].max())


def qualifies_as_donor(
    demand: pd.Series, start: date, end: date, min_median: float, min_coverage: float
) -> bool:
    reported = demand.dropna()
    expected = ((end - start).days + 1) * 24
    return len(reported) / expected >= min_coverage and float(reported.median()) >= min_median


@dataclass(frozen=True)
class SiteResult:
    site: str
    ba: str
    start: date
    expected_mw: float
    estimate_mw: float
    p: float
    low_mw: float
    high_mw: float
    threshold_mw: float
    lead_mw: float
    minus_90_mw: float
    plus_90_mw: float | None
    other_grid_p: float
    synthetic_gap_mw: float
    adjusted_p: float | None = None
    label: Claim | None = None
    revision_mw: float | None = None


def _aligned_shares(
    errors: pd.Series,
    peak: float,
    donor_errors: dict[str, pd.Series],
    donor_peaks: dict[str, float],
) -> pd.DataFrame:
    shares = {"target": errors / peak * 100}
    shares |= {code: series / donor_peaks[code] * 100 for code, series in donor_errors.items()}
    return pd.DataFrame(shares).dropna()


def score_site(
    site: str,
    ba: str,
    start: date,
    expected_mw: float,
    errors: dict[str, pd.Series],
    null: np.ndarray,
    peak: float,
    donor_errors: dict[str, pd.Series],
    donor_peaks: dict[str, float],
) -> SiteResult:
    estimate = step_estimate(errors["main"], start)
    low, high = placebo_interval(estimate, null)
    target_share = estimate / peak
    donor_shares = np.array(
        [step_estimate(series, start) / donor_peaks[code] for code, series in donor_errors.items()]
    )
    shares = _aligned_shares(errors["main"], peak, donor_errors, donor_peaks)
    moment = pd.Timestamp(start, tz="UTC")
    pre, post = shares[shares.index < moment], shares[shares.index >= moment]
    columns = [code for code in shares.columns if code != "target"]
    gap = synthetic_gap(
        pre["target"].to_numpy(),
        pre[columns].to_numpy(),
        post["target"].to_numpy(),
        post[columns].to_numpy(),
    )
    return SiteResult(
        site,
        ba,
        start,
        expected_mw,
        estimate,
        rank_p(estimate, null),
        low,
        high,
        null_threshold(null),
        step_estimate(errors["lead"], start - timedelta(days=180)),
        step_estimate(errors["minus"], start - timedelta(days=90)),
        # Amendment 5: an early run ends before this window does, so it comes later.
        step_estimate(errors["plus"], start + timedelta(days=90)) if "plus" in errors else None,
        rank_p(target_share, donor_shares),
        gap * peak / 100,
    )


def result_to_frame(result: SiteResult) -> pd.DataFrame:
    return pd.DataFrame([asdict(result)]).astype({"start": str})


def result_from_frame(frame: pd.DataFrame) -> SiteResult:
    record: dict[str, Any] = {
        str(name): value
        for name, value in frame.astype(object).where(frame.notna(), None).iloc[0].items()
    }
    return SiteResult(**{**record, "start": date.fromisoformat(str(record["start"]))})


def keep_early_result(early: SiteResult, later: SiteResult) -> SiteResult:
    """Amendment 5: the early numbers stand. The later snapshot adds one check and a revision."""
    return replace(
        early, plus_90_mw=later.plus_90_mw, revision_mw=later.estimate_mw - early.estimate_mw
    )


def with_labels(results: list[SiteResult]) -> list[SiteResult]:
    """Holm runs across the primary sites only, because only they can earn a label."""
    adjusted = holm({result.site: result.p for result in results})
    return [
        replace(
            result,
            adjusted_p=adjusted[result.site],
            label=claim(
                adjusted[result.site],
                result.estimate_mw,
                result.lead_mw,
                result.threshold_mw,
                result.other_grid_p,
                result.synthetic_gap_mw,
            ),
        )
        for result in results
    ]


def _row(result: SiteResult) -> str:
    return (
        f"| {result.site} | {BA_NAMES[result.ba]} | {result.start.isoformat()} "
        f"| {result.expected_mw:,.0f} | {result.estimate_mw:+,.0f} "
        f"| {result.low_mw:+,.0f} to {result.high_mw:+,.0f} | {result.p:.3f} "
        f"| {'' if result.adjusted_p is None else f'{result.adjusted_p:.3f}'} "
        f"| {result.label or 'secondary'} |"
    )


def _checks(result: SiteResult) -> str:
    plus = "not yet" if result.plus_90_mw is None else f"{result.plus_90_mw:+,.0f}"
    return (
        f"| {result.site} | {result.lead_mw:+,.0f} | {result.threshold_mw:+,.0f} "
        f"| {result.minus_90_mw:+,.0f} | {plus} "
        f"| {result.other_grid_p:.3f} | {result.synthetic_gap_mw:+,.0f} |"
    )


def render_event_study(
    primary: list[SiteResult], secondary: list[SiteResult], donor_count: int
) -> str:
    everything = [*primary, *secondary]
    return "\n".join(
        [
            "# M2 event study results",
            "",
            "Generated by `atlas analyze event-study`. Rules: Amendment 4 in",
            "[docs/analysis_plan.md](analysis_plan.md). Even `supported` does not prove a site",
            "caused the rise, because other new customers could explain it.",
            "",
            "| Site | Grid | Start | Expected MW | Estimate MW | 90% interval MW | p | Holm p "
            "| Label |",
            "|---|---|---|---|---|---|---|---|---|",
            *[_row(result) for result in everything],
            "",
            f"## Checks ({donor_count} control grids)",
            "",
            "| Site | Lead window MW | Threshold MW | Start -90 days MW | Start +90 days MW "
            "| Other-grid p | Synthetic gap MW |",
            "|---|---|---|---|---|---|---|",
            *[_checks(result) for result in everything],
            "",
            *[
                f"{result.site} ran early under Amendment 5. EIA's revisions moved its estimate by "
                f"{result.revision_mw:+,.1f} MW since then, which cannot change its label."
                for result in everything
                if result.revision_mw is not None
            ],
            "",
        ]
    )


def render_early_result(result: SiteResult, donor_count: int) -> str:
    return "\n".join(
        [
            "# Early M2 result: Meta Los Lunas",
            "",
            "Generated by `atlas analyze event-study-early`. Rules: Amendments 4 and 5 in",
            "[docs/analysis_plan.md](analysis_plan.md). This site ran early for timing, not",
            "because of anything in the data. Final labels come from the Holm table after the",
            "2026-12-15 run. Even a pass does not prove the site caused a rise, because other new",
            "customers could explain it.",
            "",
            f"**Reading: {early_reading(result.p)}.**",
            "",
            "| Site | Grid | Start | Expected MW | Estimate MW | 90% interval MW | p | Holm p "
            "| Label |",
            "|---|---|---|---|---|---|---|---|---|",
            _row(result).replace("| secondary |", "| set after Meta Kuna runs |"),
            "",
            f"## Checks ({donor_count} control grids)",
            "",
            "| Site | Lead window MW | Threshold MW | Start -90 days MW | Start +90 days MW "
            "| Other-grid p | Synthetic gap MW |",
            "|---|---|---|---|---|---|---|",
            _checks(result),
            "",
        ]
    )
