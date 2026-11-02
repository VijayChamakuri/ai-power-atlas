"""The app shows committed numbers, so it must run on them and agree with the written result."""

from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from atlas.ml.detectability import step_estimate
from atlas.ml.m2_figures import stacked_dots

ROOT = Path(__file__).parents[2]
DATA = ROOT / "app" / "data"


def test_app_renders_the_stored_result() -> None:
    app = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=30).run()
    assert not app.exception
    assert "64 MW" in app.title[0].value
    assert [metric.value for metric in app.metric] == ["+64 MW", "13 to 102 MW", "0.022"]


def test_extract_reproduces_the_stored_estimate() -> None:
    daily = pd.read_csv(DATA / "los_lunas_daily.csv", parse_dates=["date"])
    result = pd.read_csv(DATA / "los_lunas_result.csv").iloc[0]
    series = pd.Series(daily["residual_mw"].to_numpy(), index=daily["date"].dt.tz_localize("UTC"))
    start = pd.Timestamp(result["start"]).date()
    assert abs(step_estimate(series, start) - result["estimate_mw"]) < 0.01


def test_written_result_matches_the_extract() -> None:
    result = pd.read_csv(DATA / "los_lunas_result.csv").iloc[0]
    written = (ROOT / "docs" / "m2_early_los_lunas.md").read_text()
    assert f"| {result['estimate_mw']:+.0f} |" in written
    assert f"| {result['p']:.3f} |" in written


def test_stacked_dots_keep_values_and_stack_within_a_bin() -> None:
    heights = stacked_dots(np.array([1.0, 12.0, 3.0, 25.0, 8.0]), 10.0)
    assert heights.tolist() == [1, 1, 2, 1, 3]
