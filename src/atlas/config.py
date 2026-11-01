from datetime import date

from pydantic_settings import BaseSettings, SettingsConfigDict

# docs/analysis_plan.md fixes these values. Change them there first, as a dated amendment.
FREEZE_DATE = date(2026, 10, 31)  # Day the M1 snapshots were taken.
HISTORY_START = date(2019, 1, 1)  # Start of EIA-930 history used by the analysis plan.
CANDIDATE_SHARE = 0.02  # Starting threshold from docs/PLAN.md section 11.0.
PEAK_WINDOW_DAYS = 365  # Peak demand over the last 12 months, so one odd year does not set it.


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    eia_api_key: str = ""
    census_api_key: str = ""
    sec_contact_email: str = ""
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = ""
    minio_root_password: str = ""
