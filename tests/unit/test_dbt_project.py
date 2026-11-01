"""The marts recompute frozen results in SQL, so their thresholds must match the Python ones."""

from pathlib import Path

import yaml

from atlas.config import (
    CANDIDATE_SHARE,
    FREEZE_DATE,
    MIN_PSEUDO_DATES,
    NULL_QUANTILE,
    PEAK_WINDOW_DAYS,
    POWER_QUANTILE,
)
from atlas.ml.candidates import BAD_VALUE_MEDIAN_MULTIPLE

PROJECT = Path(__file__).parents[2] / "dbt" / "dbt_project.yml"


def test_dbt_vars_match_python_config() -> None:
    assert yaml.safe_load(PROJECT.read_text())["vars"] == {
        "freeze_date": FREEZE_DATE.isoformat(),
        "bad_value_median_multiple": BAD_VALUE_MEDIAN_MULTIPLE,
        "peak_window_days": PEAK_WINDOW_DAYS,
        "candidate_share": CANDIDATE_SHARE,
        "null_quantile": NULL_QUANTILE,
        "power_quantile": POWER_QUANTILE,
        "min_pseudo_dates": MIN_PSEUDO_DATES,
    }
