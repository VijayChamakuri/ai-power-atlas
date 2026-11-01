"""Candidate BAs are chosen by a rule fixed in docs/analysis_plan.md, never by hand."""

from datetime import date, timedelta

import pandas as pd

from atlas.config import CANDIDATE_SHARE, PEAK_WINDOW_DAYS

BAD_VALUE_MEDIAN_MULTIPLE = 3  # Same reporting-error cutoff the baseline model uses.


def clean_demand(values: pd.Series) -> pd.Series:
    """Raw hours stay in the lake. One bad spike must not set a BA's peak or train its model."""
    positive = values[values > 0]
    return positive[positive <= BAD_VALUE_MEDIAN_MULTIPLE * positive.median()]


def peak_demand(demand: pd.DataFrame, freeze: date) -> tuple[float, float, int, str]:
    """Returns cleaned peak, raw peak, dropped hours, and the last hour with data.

    The window ends at the last hour with data, per Amendment 2: a BA that stopped reporting would
    otherwise be judged on a partial year that can miss its summer peak.
    """
    values = demand.dropna(subset=["value"])
    cutoff = f"{freeze.isoformat()}T23"
    series_end = str(values[values["period"] <= cutoff]["period"].max())
    end_day = date.fromisoformat(series_end[:10])
    start = (end_day - timedelta(days=PEAK_WINDOW_DAYS)).isoformat()
    in_window = values[(values["period"] >= start) & (values["period"] <= series_end)]["value"]
    cleaned = clean_demand(values["value"]).reindex(in_window.index).dropna()
    return float(cleaned.max()), float(in_window.max()), len(in_window) - len(cleaned), series_end


def select_candidates(
    sites: pd.DataFrame, site_bas: pd.DataFrame, peaks: pd.DataFrame
) -> pd.DataFrame:
    """A site in overlapping polygons counts for each BA, per Amendment 1."""
    joined = site_bas.merge(sites[["site", "power_mw", "first_date"]], on="site")
    joined = joined.assign(ba=joined["ba_codes"].str.split(",")).explode("ba")
    joined = joined[joined["ba"].fillna("") != ""]
    totals = (
        joined.groupby("ba")
        .agg(
            site_power_mw=("power_mw", "sum"),
            site_count=("site", "count"),
            first_site_date=("first_date", "min"),
        )
        .reset_index()
    )
    table = totals.merge(peaks, on="ba", how="left")
    table["share"] = table["site_power_mw"] / table["peak_mw"]
    # A BA whose data ends before its first site can never show that site's load.
    table["candidate"] = (table["share"] >= CANDIDATE_SHARE) & (
        table["series_end"].str[:10] >= table["first_site_date"]
    )
    return table.sort_values("share", ascending=False).reset_index(drop=True)
