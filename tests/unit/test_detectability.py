"""PNM slices are real EIA-930 and Open-Meteo data pulled 2026-10-31. Its first site is 2026-03."""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from atlas.ml.baseline import fit_predict, forecast_scores
from atlas.ml.detectability import (
    detection_rate,
    go_test,
    minimum_detectable,
    null_threshold,
    pseudo_dates,
    step_estimate,
    verdict,
)
from atlas.ml.features import FEATURES, build_features, weighted_weather

FIXTURES = Path(__file__).parents[1] / "fixtures" / "eia"


@pytest.fixture(scope="module")
def daily() -> pd.Series:
    frame = pd.read_csv(FIXTURES / "pnm_daily_demand_20261031.csv")
    return frame.set_index(pd.to_datetime(frame["day"], utc=True))["demand_mw"]


@pytest.fixture(scope="module")
def hourly() -> pd.DataFrame:
    raw = pd.read_parquet(FIXTURES / "pnm_hourly_20261031.parquet").set_index("hour")
    weather = raw.reset_index().assign(time=lambda frame: frame["hour"])
    features = build_features(weighted_weather({"a": weather}, {"a": 1.0}), "America/Denver")
    return features.join(raw["demand"])


def test_last_window_ends_before_the_first_site() -> None:
    dates = pseudo_dates(date(2019, 1, 1), date(2023, 8, 2), date(2026, 10, 31))
    assert dates[0] == date(2021, 12, 31)
    assert (date(2023, 8, 2) - dates[-1]).days > 180
    assert (date(2023, 8, 2) - dates[-1]).days <= 210


def test_series_end_also_limits_pseudo_dates() -> None:
    assert pseudo_dates(date(2019, 1, 1), date(2030, 1, 1), date(2022, 3, 1)) == []


def test_formula_matches_detection_rate_on_real_demand(daily: pd.Series) -> None:
    centered = daily - daily.rolling(365, center=True, min_periods=180).mean()
    dates = pseudo_dates(date(2019, 1, 1), date(2024, 12, 31), date(2024, 12, 31))
    estimates = np.array([step_estimate(centered, t) for t in dates])
    assert len(estimates) >= 12
    mde = minimum_detectable(estimates)
    assert detection_rate(estimates, 0.0) <= 0.10
    assert detection_rate(estimates, mde) == pytest.approx(0.8, abs=0.1)
    assert detection_rate(estimates, mde * 2) >= 0.8


def test_step_in_real_demand_moves_the_estimate_by_exactly_the_step(daily: pd.Series) -> None:
    t = date(2022, 6, 1)
    moment = pd.Timestamp(t, tz="UTC")
    injected = daily.where(daily.index < moment, daily + 100.0)
    assert step_estimate(injected, t) - step_estimate(daily, t) == pytest.approx(100.0)


def test_step_after_training_leaves_the_model_alone(hourly: pd.DataFrame) -> None:
    cut = pd.Timestamp("2022-01-01", tz="UTC")
    train, future = hourly[hourly.index < cut], hourly[hourly.index >= cut]
    assert fit_predict(train, future).equals(fit_predict(train, future.assign(demand=0.0)))


def test_model_extrapolates_a_trend_trees_cannot(hourly: pd.DataFrame) -> None:
    cut = pd.Timestamp("2022-01-01", tz="UTC")
    train, future = hourly[hourly.index < cut].copy(), hourly[hourly.index >= cut]
    grown = train.assign(demand=train["demand"] + np.arange(len(train)) * 0.1)
    plain = fit_predict(train, future)
    assert (fit_predict(grown, future) - plain).mean() > 0.1 * len(train) * 0.9


def test_real_out_of_sample_fit_is_plausible(hourly: pd.DataFrame) -> None:
    cut = pd.Timestamp("2022-01-01", tz="UTC")
    train, future = hourly[hourly.index < cut], hourly[hourly.index >= cut]
    scores = forecast_scores(future["demand"], fit_predict(train, future))
    assert 1 < scores["mape"] < 15
    assert not any("lag" in name for name in FEATURES)


def test_threshold_is_the_95th_percentile() -> None:
    assert null_threshold(np.arange(101.0)) == pytest.approx(95.0)


def _sites(flagged: bool = False) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site": ["a"],
            "power_mw": [100.0],
            "first_date": ["2025-01-01"],
            "behind_meter_risk": [flagged],
        }
    )


@pytest.mark.parametrize(
    ("flagged", "codes", "mde", "expected"),
    [
        (False, "X", 50.0, "go"),
        (False, "X", 90.0, "go_weak_evidence"),
        (False, "X", 150.0, "pivot"),
        (True, "X", 50.0, "pivot"),
        (False, "X,Y", 50.0, "pivot"),
        (False, "X", None, "pivot"),
    ],
)
def test_go_rule(flagged: bool, codes: str, mde: float | None, expected: str) -> None:
    site_bas = pd.DataFrame({"site": ["a"], "ba_codes": [codes]})
    bas = pd.DataFrame({"ba": ["X", "Y"], "mde_mw": [mde, mde]})
    assert verdict(go_test(_sites(flagged), site_bas, bas)) == expected
