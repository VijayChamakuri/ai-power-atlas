import numpy as np
import pandas as pd

from atlas.ml.detectability import BaResult
from atlas.ml.report import render_results


def test_missing_scores_and_mde_render_blank_not_nan() -> None:
    scores = {"mape": 4.0, "rmse": 700.0, "peak_hour_mae": 700.0}
    missing = {"mape": float("nan"), "rmse": float("nan"), "peak_hour_mae": float("nan")}
    results = {
        "AEP": BaResult(
            "AEP",
            "ok",
            2,
            np.array([1.0, 2.0, 3.0, 5.0, 8.0, 13.0]),
            mde_mw=590.0,
            scores={"model": scores, "seasonal_naive": scores, "eia_day_ahead": missing},
        ),
        "SWPP": BaResult("SWPP", "insufficient_history", 7),
    }
    table = pd.DataFrame(columns=["mde_mw"])
    sites = pd.DataFrame(columns=["site", "power_mw", "behind_meter_risk"])
    seed = pd.DataFrame(columns=["site"])
    report = render_results(
        results, pd.DataFrame({"ba": [], "peak_mw": []}), table, sites, seed, "abc1234", "pivot"
    )
    assert "nan" not in report
    assert "| SWPP | insufficient_history | 7 |" in report
