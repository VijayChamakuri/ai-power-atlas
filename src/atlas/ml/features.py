"""No lagged demand anywhere here: lags would absorb the step this model exists to expose."""

import holidays
import numpy as np
import pandas as pd

DEGREE_HOUR_BASE_F = 65.0  # The base used in US degree-day reporting.
FEATURES = [
    "hour",
    "day_of_week",
    "month",
    "holiday",
    "temperature_f",
    "humidity",
    "cooling_degree",
    "heating_degree",
]


def to_utc_index(periods: pd.Series) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(periods, utc=True, format="%Y-%m-%dT%H"))


def weighted_weather(
    frames: dict[str, pd.DataFrame], populations: dict[str, float]
) -> pd.DataFrame:
    """Each frame is one county's hourly weather, with `time` in GMT."""
    total = sum(populations.values())
    parts = []
    for fips, frame in frames.items():
        indexed = frame.set_index(pd.to_datetime(frame["time"], utc=True))
        columns = indexed[["temperature_2m", "relative_humidity_2m"]]
        parts.append(columns * (populations[fips] / total))
    combined = pd.concat(parts).groupby(level=0).sum(min_count=1)
    return combined.rename(
        columns={"temperature_2m": "temperature_f", "relative_humidity_2m": "humidity"}
    )


def build_features(weather: pd.DataFrame, timezone: str) -> pd.DataFrame:
    local = pd.DatetimeIndex(weather.index).tz_convert(timezone)
    federal = holidays.country_holidays("US", years=sorted(set(local.year)))
    frame = weather.assign(
        hour=local.hour,
        day_of_week=local.day_of_week,
        month=local.month,
        holiday=np.isin(local.date, np.array(list(federal.keys()))).astype(int),
        cooling_degree=(weather["temperature_f"] - DEGREE_HOUR_BASE_F).clip(lower=0),
        heating_degree=(DEGREE_HOUR_BASE_F - weather["temperature_f"]).clip(lower=0),
    )
    return frame[FEATURES]
