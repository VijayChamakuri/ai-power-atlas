"""Smallest step each BA could show, measured only on windows that end before its first site."""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from atlas.config import (
    MIN_HISTORY_DAYS,
    MIN_PSEUDO_DATES,
    NULL_QUANTILE,
    POST_DAYS,
    POWER_QUANTILE,
    PSEUDO_STEP_DAYS,
    TRAIN_GAP_DAYS,
    WEAK_UTILIZATION,
)
from atlas.ml.baseline import fit_predict, forecast_scores
from atlas.ml.candidates import clean_demand

PRE_DAYS = TRAIN_GAP_DAYS  # The whole gap between training and t is the pre-window.


def pseudo_dates(history_start: date, first_site: date, series_end: date) -> list[date]:
    """The last post-window must end before the first site, which keeps the real effect out."""
    first = history_start + timedelta(days=MIN_HISTORY_DAYS + TRAIN_GAP_DAYS)
    dates = []
    current = first
    while (
        current + timedelta(days=POST_DAYS) < first_site
        and current + timedelta(days=POST_DAYS) <= series_end
    ):
        dates.append(current)
        current += timedelta(days=PSEUDO_STEP_DAYS)
    return dates


def step_estimate(daily_residuals: pd.Series, t: date) -> float:
    """Mean residual in the 180 days after t, minus the mean in the 365 days before it."""
    moment = pd.Timestamp(t, tz="UTC")
    pre = daily_residuals[
        (daily_residuals.index >= moment - pd.Timedelta(days=PRE_DAYS))
        & (daily_residuals.index < moment)
    ]
    post = daily_residuals[
        (daily_residuals.index >= moment)
        & (daily_residuals.index < moment + pd.Timedelta(days=POST_DAYS))
    ]
    return float(post.mean() - pre.mean())


def null_threshold(estimates: np.ndarray) -> float:
    return float(np.quantile(estimates, NULL_QUANTILE))


def minimum_detectable(estimates: np.ndarray) -> float:
    """Adding S MW after t adds exactly S to e(t), so this is the step found in 80% of windows."""
    return null_threshold(estimates) - float(np.quantile(estimates, POWER_QUANTILE))


def detection_rate(estimates: np.ndarray, step: float) -> float:
    return float(np.mean(estimates + step > null_threshold(estimates)))


@dataclass
class BaResult:
    ba: str
    status: str
    dates: int
    estimates: np.ndarray = field(default_factory=lambda: np.array([]))
    mde_mw: float | None = None
    rate_at_zero: float | None = None
    rate_at_mde: float | None = None
    injected_rate: float | None = None
    dropped_hours: int = 0
    scores: dict[str, dict[str, float]] = field(default_factory=dict)


def _daily_residuals(actual: pd.Series, predicted: pd.Series) -> pd.Series:
    residuals = (actual - predicted).dropna()
    return residuals.groupby(pd.DatetimeIndex(residuals.index).floor("D")).mean()


def analyze_ba(
    ba: str,
    demand: pd.Series,
    forecast: pd.Series,
    features: pd.DataFrame,
    history_start: date,
    first_site: date,
    series_end: date,
) -> BaResult:
    dates = pseudo_dates(history_start, first_site, series_end)
    if len(dates) < MIN_PSEUDO_DATES:
        return BaResult(ba, "insufficient_history", len(dates))

    cleaned = clean_demand(demand.dropna())
    frame = features.join(cleaned.rename("demand"), how="inner").dropna()
    estimates: list[float] = []
    windows: list[tuple[date, pd.Series]] = []
    for t in dates:
        moment = pd.Timestamp(t, tz="UTC")
        train_end = moment - pd.Timedelta(days=TRAIN_GAP_DAYS)
        window_end = moment + pd.Timedelta(days=POST_DAYS)
        future = frame[(frame.index >= train_end) & (frame.index < window_end)]
        predicted = fit_predict(frame[frame.index < train_end], future)
        estimates.append(step_estimate(_daily_residuals(future["demand"], predicted), t))
        windows.append((t, predicted))

    values = np.array(estimates)
    mde = minimum_detectable(values)
    result = BaResult(
        ba,
        "ok",
        len(dates),
        values,
        mde,
        detection_rate(values, 0.0),
        detection_rate(values, mde),
        _injected_rate(frame["demand"], windows, null_threshold(values), mde),
        int(demand.notna().sum() - len(cleaned)),
    )

    # Scores use the newest window, the closest to how the model would be used on a real date.
    predicted = windows[-1][1]
    actual = frame["demand"].reindex(predicted.index)
    result.scores = {
        "model": forecast_scores(actual, predicted),
        "seasonal_naive": forecast_scores(actual, cleaned.shift(freq=pd.Timedelta(hours=168))),
        "eia_day_ahead": forecast_scores(actual, forecast),
    }
    return result


def _injected_rate(
    demand: pd.Series, windows: list[tuple[date, pd.Series]], threshold: float, step: float
) -> float:
    """Adds the step to real demand and re-measures, instead of trusting the formula's algebra."""
    hits = 0
    for t, predicted in windows:
        moment = pd.Timestamp(t, tz="UTC")
        injected = demand.reindex(predicted.index)
        injected = injected.where(injected.index < moment, injected + step)
        hits += step_estimate(_daily_residuals(injected, predicted), t) > threshold
    return hits / len(windows)


def go_test(sites: pd.DataFrame, site_bas: pd.DataFrame, bas: pd.DataFrame) -> pd.DataFrame:
    """One row per site and BA. `bas` holds candidate BAs and their mde_mw, null if none."""
    joined = site_bas.merge(sites, on="site")
    joined["overlap"] = joined["ba_codes"].str.contains(",")
    exploded = joined.assign(ba=joined["ba_codes"].str.split(",")).explode("ba")
    table = exploded.merge(bas[["ba", "mde_mw"]].astype({"mde_mw": float}), on="ba")
    table["implied_utilization"] = table["mde_mw"] / table["power_mw"]
    table["above_mde"] = table["power_mw"] >= table["mde_mw"]
    table["eligible"] = ~table["behind_meter_risk"] & ~table["overlap"] & table["mde_mw"].notna()
    table["passes_go"] = table["eligible"] & table["above_mde"]
    return table.sort_values(["passes_go", "implied_utilization"], ascending=[False, True])


def verdict(table: pd.DataFrame) -> str:
    """Vijay makes the decision. This only reports what the plan's rule says."""
    passing = table[table["passes_go"]]
    if passing.empty:
        return "pivot"
    if (passing["implied_utilization"] > WEAK_UTILIZATION).all():
        return "go_weak_evidence"
    return "go"
