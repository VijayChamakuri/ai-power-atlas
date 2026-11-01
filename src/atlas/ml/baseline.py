"""Weather normalization, not forecasting. It should lose to EIA's forecast at short horizons."""

import lightgbm as lgb
import numpy as np
import pandas as pd

from atlas.config import LIGHTGBM_PARAMS
from atlas.ml.features import FEATURES


def _hours(index: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(index.as_unit("s").asi8, dtype=float) / 3600.0


def fit_predict(train: pd.DataFrame, future: pd.DataFrame) -> pd.Series:
    """Trees cannot extrapolate, and a flat trend would read as new load, so detrend first."""
    assert isinstance(train.index, pd.DatetimeIndex)
    assert isinstance(future.index, pd.DatetimeIndex)
    slope, intercept = np.polyfit(_hours(train.index), train["demand"].to_numpy(), 1)
    detrended = train["demand"] - (slope * _hours(train.index) + intercept)
    model = lgb.LGBMRegressor(**LIGHTGBM_PARAMS)
    model.fit(train[FEATURES], detrended)
    predicted = np.asarray(model.predict(future[FEATURES]), dtype=float)
    return pd.Series(predicted + slope * _hours(future.index) + intercept, index=future.index)


def forecast_scores(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    """Peak-hour error is the absolute error at each day's highest actual hour."""
    joined = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    error = joined["actual"] - joined["predicted"]
    peak_hours = joined["actual"].groupby(pd.DatetimeIndex(joined.index).floor("D")).idxmax()
    return {
        "mape": float((error.abs() / joined["actual"]).mean() * 100),
        "rmse": float(np.sqrt((error**2).mean())),
        "peak_hour_mae": float(error.loc[peak_hours].abs().mean()),
    }
