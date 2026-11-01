"""Slices of the real Epoch files, pulled 2026-10-31."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from atlas.ingest.datacenters import apply_flag_seeds, build_sites, matched_terms

FIXTURES = Path(__file__).parents[1] / "fixtures" / "epoch"


@pytest.fixture
def sites() -> pd.DataFrame:
    built = build_sites(
        pd.read_csv(FIXTURES / "data_centers_20261031.csv"),
        pd.read_csv(FIXTURES / "timelines_20261031.csv"),
        date(2026, 10, 31),
    )
    return built.set_index("site")


def test_non_us_sites_are_excluded(sites: pd.DataFrame) -> None:
    assert "DayOne Nusajaya" not in sites.index
    assert len(sites) == 4


def test_power_is_total_power_not_it_power(sites: pd.DataFrame) -> None:
    assert sites.loc["Anthropic-Amazon New Carlisle", "power_mw"] == 1244
    assert sites.loc["Colossus 2", "power_mw"] == 1276


def test_later_rows_never_set_power_or_dates(sites: pd.DataFrame) -> None:
    earlier = build_sites(
        pd.read_csv(FIXTURES / "data_centers_20261031.csv"),
        pd.read_csv(FIXTURES / "timelines_20261031.csv"),
        date(2025, 1, 1),
    ).set_index("site")
    assert earlier.loc["Colossus 2", "power_mw"] == 0
    assert earlier["first_date"].isna()["Colossus 2"]
    assert sites.loc["Colossus 2", "first_date"] == "2025-10-19"


def test_site_with_no_power_has_no_first_date(sites: pd.DataFrame) -> None:
    assert sites.loc["Anthropic Barber Lake", "power_mw"] == 0
    assert sites["first_date"].isna()["Anthropic Barber Lake"]


def test_flag_catches_epoch_text_and_ignores_backup_generators(sites: pd.DataFrame) -> None:
    assert sites.loc["Colossus 2", "behind_meter_risk"]
    assert not sites.loc["Anthropic-Amazon New Carlisle", "behind_meter_risk"]
    assert matched_terms("Most of the 120 backup diesel generators are in place.") == ""
    assert matched_terms("likely for on-site POWER generation") == "on-site power,power generation"


def test_seed_adds_a_flag_and_keeps_existing_terms(sites: pd.DataFrame) -> None:
    table = sites.reset_index()
    seeds = pd.DataFrame({"site": ["Colossus 2", "Google Storey County"]})
    flagged = apply_flag_seeds(table, seeds).set_index("site")
    assert str(flagged.loc["Google Storey County", "behind_meter_terms"]).endswith("hand_seed")
    assert flagged.loc["Colossus 2", "behind_meter_terms"] == "turbine,hand_seed"
    assert not flagged.loc["Anthropic-Amazon New Carlisle", "behind_meter_risk"]


def test_seed_with_unknown_site_fails(sites: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="unknown"):
        apply_flag_seeds(sites.reset_index(), pd.DataFrame({"site": ["Not A Site"]}))
