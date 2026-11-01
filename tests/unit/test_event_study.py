"""Uses only PNM demand from before its first site, so no real effect can leak into these tests."""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from atlas import config
from atlas.ml import event_study as es
from atlas.ml.detectability import pseudo_dates, step_estimate
from atlas.ml.features import build_features, weighted_weather

FIXTURE = Path(__file__).parents[1] / "fixtures" / "eia" / "pnm_daily_demand_20261031.csv"


@pytest.fixture(scope="module")
def null() -> np.ndarray:
    frame = pd.read_csv(FIXTURE)
    daily = frame.set_index(pd.to_datetime(frame["day"], utc=True))["demand_mw"]
    centered = daily - daily.rolling(365, center=True, min_periods=180).mean()
    dates = pseudo_dates(date(2019, 1, 1), date(2024, 12, 31), date(2024, 12, 31))
    return np.array([step_estimate(centered, t) for t in dates])


def test_nothing_runs_before_the_freeze_as_committed() -> None:
    assert config.M2_FREEZE_DATE == date(2026, 12, 15)
    with pytest.raises(es.EventStudyLockedError, match="freeze"):
        es.require_unlocked(date(2026, 12, 14))


def test_lock_needs_approval_even_after_the_freeze() -> None:
    with pytest.raises(es.EventStudyLockedError, match="not been approved"):
        es.require_unlocked(date(2030, 1, 1), approved=False)


def test_lock_opens_only_on_the_freeze_date_or_later() -> None:
    es.require_unlocked(date(2026, 12, 15), approved=True)


def test_rank_p_at_its_extremes(null: np.ndarray) -> None:
    assert es.rank_p(float(null.max()) + 1, null) == pytest.approx(1 / (len(null) + 1))
    assert es.rank_p(float(null.min()) - 1, null) == 1.0


def test_false_alarm_rate_on_real_null_is_near_five_percent(null: np.ndarray) -> None:
    left_out = [es.rank_p(float(value), np.delete(null, index)) for index, value in enumerate(null)]
    assert np.mean(np.array(left_out) <= 0.05) <= 0.10


def test_interval_holds_an_injected_step_in_real_noise(null: np.ndarray) -> None:
    step = 150.0
    low, high = es.placebo_interval(float(np.median(null)) + step, null)
    assert low < step < high


def test_holm_matches_a_worked_example_and_stays_ordered() -> None:
    adjusted = es.holm({"a": 0.02, "b": 0.03})
    assert adjusted == {"a": pytest.approx(0.04), "b": pytest.approx(0.04)}
    assert es.holm({"a": 0.5, "b": 0.8}) == {"a": 1.0, "b": 1.0}


def test_synthetic_control_recovers_known_weights_and_step() -> None:
    rng = np.random.default_rng(3)
    donors = rng.normal(size=(500, 3))
    weights = np.array([0.7, 0.3, 0.0])
    target = donors @ weights
    assert es.synthetic_weights(target[:365], donors[:365]) == pytest.approx(weights, abs=0.01)
    gap = es.synthetic_gap(target[:365], donors[:365], target[365:] + 2.0, donors[365:])
    assert gap == pytest.approx(2.0, abs=0.02)


@pytest.mark.parametrize(
    ("adjusted", "estimate", "lead", "other", "gap", "expected"),
    [
        (0.04, 100.0, 5.0, 0.05, 50.0, "supported"),
        (0.04, 100.0, 50.0, 0.05, 50.0, "suggestive"),
        (0.04, 100.0, 5.0, 0.30, 50.0, "suggestive"),
        (0.04, 100.0, 5.0, 0.05, -1.0, "suggestive"),
        (0.05, 100.0, 5.0, 0.05, 50.0, "null"),
    ],
)
def test_claim_rule(
    adjusted: float, estimate: float, lead: float, other: float, gap: float, expected: str
) -> None:
    assert es.claim(adjusted, estimate, lead, 26.0, other, gap) == expected


@pytest.fixture(scope="module")
def hourly() -> pd.DataFrame:
    raw = pd.read_parquet(FIXTURE.parent / "pnm_hourly_20261031.parquet").set_index("hour")
    weather = raw.reset_index().assign(time=lambda frame: frame["hour"])
    features = build_features(weighted_weather({"a": weather}, {"a": 1.0}), "America/Denver")
    return features.join(raw["demand"])


def test_step_in_real_pre_site_demand_moves_the_estimate_by_the_step(hourly: pd.DataFrame) -> None:
    t = date(2022, 7, 1)
    moment = pd.Timestamp(t, tz="UTC")
    features = hourly.drop(columns="demand")
    demand = hourly["demand"]
    base = step_estimate(es.daily_errors(demand, features, t), t)
    stepped = demand.where(demand.index < moment, demand + 100.0)
    assert step_estimate(es.daily_errors(stepped, features, t), t) - base == pytest.approx(100.0)


def test_donor_rule_needs_size_and_coverage() -> None:
    index = pd.date_range("2024-01-01", periods=240, freq="h", tz="UTC")
    start, end = date(2024, 1, 1), date(2024, 1, 10)
    assert es.qualifies_as_donor(pd.Series(600.0, index), start, end, 500, 0.95)
    assert not es.qualifies_as_donor(pd.Series(400.0, index), start, end, 500, 0.95)
    assert not es.qualifies_as_donor(pd.Series(600.0, index[:120]), start, end, 500, 0.95)


def _result(site: str, p: float) -> es.SiteResult:
    return es.SiteResult(
        site,
        "PNM",
        date(2026, 3, 1),
        114.0,
        90.0,
        p,
        10.0,
        150.0,
        40.0,
        5.0,
        40.0,
        80.0,
        0.08,
        60.0,
    )


def test_labels_use_holm_across_primary_sites() -> None:
    labeled = {r.site: r for r in es.with_labels([_result("a", 0.0204), _result("b", 0.4)])}
    assert labeled["a"].label == "supported"
    assert labeled["a"].adjusted_p == pytest.approx(0.0408)
    assert labeled["b"].label == "null"


def test_report_states_limits_and_marks_secondary_results() -> None:
    primary = es.with_labels([_result("a", 0.0204)])
    report = es.render_event_study(primary, [_result("c", 0.3)], 28)
    assert "does not prove" in report
    assert "| c | PNM (New Mexico) |" in report
    assert "secondary" in report
    assert "28 control grids" in report
