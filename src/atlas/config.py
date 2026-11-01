from datetime import date
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

# docs/analysis_plan.md fixes these values. Change them there first, as a dated amendment.
FREEZE_DATE = date(2026, 10, 31)  # Day the M1 snapshots were taken.
HISTORY_START = date(2019, 1, 1)  # Start of EIA-930 history used by the analysis plan.
CANDIDATE_SHARE = 0.02  # Starting threshold from docs/PLAN.md section 11.0.
PEAK_WINDOW_DAYS = 365  # Peak demand over the last 12 months, so one odd year does not set it.

# Detectability windows and error rates, from docs/analysis_plan.md.
PSEUDO_STEP_DAYS = 30
TRAIN_GAP_DAYS = 365  # Training stops a year before t, so the pre-window is also out of sample.
MIN_HISTORY_DAYS = 730  # Two years, so the trend is not fit on a single season.
POST_DAYS = 180
MIN_PSEUDO_DATES = 12  # About one year of starting points.
NULL_QUANTILE = 0.95  # One-sided 5% false positive rate.
POWER_QUANTILE = 0.20  # A step clears the threshold in 80% of windows.
WEAK_UTILIZATION = 0.80  # Judgment call, fixed before results. See the go or pivot section.

# LightGBM's usual starting values, not tuned: tuning against the null would shrink the MDE.
LIGHTGBM_PARAMS: dict[str, Any] = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "random_state": 1,
    "deterministic": True,
    "force_row_wise": True,
    "n_jobs": 4,
    "verbose": -1,
}

# EIA-930 hours are UTC, but load follows local time. Each BA uses the zone of most of its load.
BA_TIMEZONES = {
    "AEP": "America/New_York",
    "AZPS": "America/Phoenix",
    "BPAT": "America/Los_Angeles",
    "ERCO": "America/Chicago",
    "IPCO": "America/Boise",
    "NEVP": "America/Los_Angeles",
    "PACW": "America/Los_Angeles",
    "PGE": "America/Los_Angeles",
    "PJM": "America/New_York",
    "PNM": "America/Denver",
    "SOCO": "America/New_York",
    "SRP": "America/Phoenix",
    "SWPP": "America/Chicago",
    "TVA": "America/Chicago",
    "WALC": "America/Phoenix",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    eia_api_key: str = ""
    census_api_key: str = ""
    sec_contact_email: str = ""
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = ""
    minio_root_password: str = ""
    mlflow_tracking_uri: str = "http://localhost:5001"
