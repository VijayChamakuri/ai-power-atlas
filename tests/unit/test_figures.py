import numpy as np
import pandas as pd

from atlas.ml import figures


def test_status_follows_the_order_of_the_go_test() -> None:
    sites = pd.DataFrame(
        {
            "site": ["pass", "flag", "overlap", "below", "none"],
            "power_mw": [100.0, 100.0, 100.0, 10.0, 10.0],
            "behind_meter_risk": [False, True, False, False, False],
        }
    )
    site_bas = pd.DataFrame({"site": sites["site"], "ba_codes": ["A", "A", "A,B", "A", "C"]})
    table = pd.DataFrame(
        {
            "site": ["pass", "flag", "overlap", "below", "none"],
            "passes_go": [True, False, False, False, False],
            "mde_mw": [50.0, 50.0, 50.0, 50.0, None],
        }
    )
    status = figures.site_status(table, sites, site_bas).set_index("site")["status"].to_dict()
    assert status == {
        "pass": "passes",
        "flag": "excluded",
        "overlap": "excluded",
        "below": "below_limit",
        "none": "no_number",
    }


def test_albers_puts_the_projection_center_at_the_origin() -> None:
    x, y = figures.albers(np.array([-96.0]), np.array([37.5]))
    assert abs(x[0]) < 1e-9
    assert abs(y[0]) < 1e-9


def test_west_is_left_of_east_and_north_is_above_south() -> None:
    x, y = figures.albers(np.array([-120.0, -75.0]), np.array([30.0, 45.0]))
    assert x[0] < x[1]
    assert y[0] < y[1]


def test_site_names_lose_only_the_operator_prefix() -> None:
    assert figures.short_name("Anthropic-Amazon New Carlisle") == "New Carlisle"
    assert figures.short_name("Meta Kuna") == "Meta Kuna"
