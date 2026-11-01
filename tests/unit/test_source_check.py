"""Cassettes in tests/fixtures/cassettes are real responses recorded on 2026-10-31."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from atlas.config import Settings
from atlas.source_check import USER_AGENT, Result, Source, build_sources, probe, render_report

RECORDED_ON = datetime(2026, 10, 31, tzinfo=UTC)
# model_construct skips .env, so a developer's real keys cannot change test results.
NO_KEYS = Settings.model_construct(eia_api_key="", census_api_key="", sec_contact_email="")
EIA_KEY = Settings.model_construct(
    eia_api_key="replay-only", census_api_key="", sec_contact_email=""
)
SEC_CONTACT = Settings.model_construct(
    eia_api_key="", census_api_key="", sec_contact_email="contact@example.org"
)


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    # Dates in the query move with the clock, and keys and contact details must not be stored.
    return {
        "match_on": ["method", "scheme", "host", "path"],
        "filter_query_parameters": ["api_key", "key"],
        "filter_headers": ["user-agent"],
    }


@pytest.fixture(scope="module")
def vcr_cassette_dir() -> str:
    return str(Path(__file__).parents[1] / "fixtures" / "cassettes")


def source_named(key: str) -> Source:
    return next(source for source in build_sources(RECORDED_ON) if source.key == key)


def check(key: str, settings: Settings) -> Result:
    # Overpass answers 406 to the default httpx User-Agent, so this must match run_checks.
    with httpx.Client(
        follow_redirects=True, timeout=60, headers={"User-Agent": USER_AGENT}
    ) as client:
        return probe(source_named(key), client, settings)


@pytest.mark.vcr
@pytest.mark.parametrize(
    ("key", "settings"),
    [
        ("eia_930_region", EIA_KEY),
        ("epoch_timelines", NO_KEYS),
        ("open_meteo", NO_KEYS),
        ("us_drought_monitor", NO_KEYS),
        ("osm_overpass", NO_KEYS),
        ("sec_edgar", SEC_CONTACT),
    ],
)
def test_data_sources_return_records(key: str, settings: Settings) -> None:
    result = check(key, settings)
    assert result.status == "ok"
    assert result.last_updated
    assert result.row_count is not None and result.row_count > 0


@pytest.mark.vcr
def test_epoch_inventory_has_rows_but_no_date_column() -> None:
    result = check("epoch_data_centers", NO_KEYS)
    assert result.status == "ok"
    assert result.last_updated is None
    assert result.row_count is not None and result.row_count > 0


@pytest.mark.vcr
def test_ba_layer_returns_polygon_records() -> None:
    result = check("ba_territories", NO_KEYS)
    assert result.status == "ok"
    assert result.row_count is not None and result.row_count > 50


@pytest.mark.vcr
def test_landing_page_never_claims_a_row_count() -> None:
    result = check("census_tiger", NO_KEYS)
    assert result.status == "page_only"
    assert result.row_count is None


@pytest.mark.vcr
def test_bot_wall_is_blocked_not_reachable() -> None:
    assert check("lbnl_queued_up", NO_KEYS).status == "blocked"


@pytest.mark.vcr
def test_plan_url_that_moved_is_unreachable() -> None:
    gone = Source("gone", 2, "https://epoch.ai/data/data_centers/gpu_clusters.csv")
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        result = probe(gone, client, NO_KEYS)
    assert result.status == "unreachable"
    assert result.detail == "HTTP 404"


def test_rate_limit_is_not_reported_as_unreachable() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(429))
    with httpx.Client(transport=transport) as client:
        result = probe(source_named("eia_retail_sales"), client, EIA_KEY)
    assert result.status == "rate_limited"


def test_rejected_census_key_is_a_key_problem() -> None:
    page = "<html><head><title>Invalid Key</title></head></html>"
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=page))
    settings = Settings.model_construct(
        eia_api_key="", census_api_key="replay-only", sec_contact_email=""
    )
    with httpx.Client(transport=transport) as client:
        result = probe(source_named("census_acs"), client, settings)
    assert result.status == "needs_key"
    assert "rejected" in result.detail


def test_eia_403_is_a_key_problem() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(403))
    with httpx.Client(transport=transport) as client:
        result = probe(source_named("eia_retail_sales"), client, EIA_KEY)
    assert result.status == "needs_key"
    assert "rejected" in result.detail


def test_missing_key_skips_the_request() -> None:
    with httpx.Client() as client:
        result = probe(source_named("eia_930_region"), client, NO_KEYS)
    assert result.status == "needs_key"
    assert "EIA_API_KEY" in result.detail


def test_every_plan_row_has_a_probe() -> None:
    assert {source.plan_row for source in build_sources(RECORDED_ON)} == set(range(1, 16))


def test_report_leaves_unknown_counts_blank() -> None:
    result = Result(source_named("census_tiger"), "page_only")
    report = render_report([result], RECORDED_ON)
    assert (
        "| 12 | [census_tiger](https://www2.census.gov/geo/tiger/) | page_only |  |  |  |" in report
    )
