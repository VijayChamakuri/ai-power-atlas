from datetime import date

import pandas as pd

from atlas.ml.candidates import peak_demand, select_candidates


def test_spike_does_not_set_the_peak_and_is_counted() -> None:
    # Values shaped like the EIA-930 errors the analysis plan names: a spike and a negative hour.
    periods = [f"2026-10-{day:02}T00" for day in range(1, 8)]
    values = [100.0, 110.0, 120.0, 105.0, 95.0, 5000.0, -3.0]
    demand = pd.DataFrame({"period": periods, "value": values})
    cleaned, raw, dropped, _ = peak_demand(demand, date(2026, 10, 31))
    assert (cleaned, raw, dropped) == (120.0, 5000.0, 2)


def test_window_ends_where_a_series_stops() -> None:
    # Shaped like WACM, whose EIA-930 demand stops on 2026-04-02.
    demand = pd.DataFrame(
        {
            "period": ["2024-03-01T18", "2025-07-01T18", "2026-04-02T18"],
            "value": [500.0, 130.0, 100.0],
        }
    )
    peak, _, _, series_end = peak_demand(demand, date(2026, 10, 31))
    assert peak == 130.0
    assert series_end == "2026-04-02T18"


def test_hours_outside_the_window_do_not_set_the_peak() -> None:
    demand = pd.DataFrame({"period": ["2020-07-01T18", "2026-07-01T18"], "value": [150.0, 100.0]})
    assert peak_demand(demand, date(2026, 10, 31))[0] == 100.0


def test_overlap_site_counts_for_each_ba_and_threshold_is_inclusive() -> None:
    sites = pd.DataFrame(
        {"site": ["a", "b"], "power_mw": [20.0, 5.0], "first_date": ["2024-01-01", "2023-06-01"]}
    )
    site_bas = pd.DataFrame({"site": ["a", "b"], "ba_codes": ["X,Y", "Y"]})
    peaks = pd.DataFrame(
        {"ba": ["X", "Y"], "peak_mw": [1000.0, 5000.0], "series_end": ["2026-10-31T23"] * 2}
    )
    table = select_candidates(sites, site_bas, peaks).set_index("ba")
    assert table.loc["X", "share"] == 0.02
    assert table.loc["X", "candidate"]
    assert table.loc["Y", "site_power_mw"] == 25
    assert table.loc["Y", "first_site_date"] == "2023-06-01"
    assert not table.loc["Y", "candidate"]


def test_series_ending_before_the_first_site_is_not_a_candidate() -> None:
    sites = pd.DataFrame({"site": ["a"], "power_mw": [182.0], "first_date": ["2026-07-25"]})
    site_bas = pd.DataFrame({"site": ["a"], "ba_codes": ["WACM"]})
    peaks = pd.DataFrame({"ba": ["WACM"], "peak_mw": [8150.0], "series_end": ["2026-04-02T18"]})
    table = select_candidates(sites, site_bas, peaks)
    assert table["share"].iloc[0] > 0.02
    assert not table["candidate"].iloc[0]
