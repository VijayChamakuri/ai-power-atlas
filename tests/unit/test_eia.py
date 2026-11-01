"""The cassette is a real EIA response recorded 2026-10-31, paged small to exercise paging."""

import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pyarrow.fs as pafs
import pytest

from atlas.contracts.eia import REGION
from atlas.ingest.eia import (
    REGION_URL,
    EiaError,
    fetch_rows,
    ingest_recent,
    month_window,
    months,
    to_frame,
)
from atlas.lake.io import get_frame


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    return {
        "match_on": ["method", "scheme", "host", "path", "query"],
        "filter_query_parameters": [("api_key", "replay-only")],
        "filter_headers": ["user-agent"],
    }


@pytest.fixture(scope="module")
def vcr_cassette_dir() -> str:
    return str(Path(__file__).parents[1] / "fixtures" / "cassettes")


@pytest.mark.vcr
def test_fetch_rows_follows_pages_to_the_total() -> None:
    with httpx.Client(timeout=60) as client:
        rows = fetch_rows(
            client,
            REGION_URL,
            os.environ.get("EIA_API_KEY", "replay-only"),
            {"respondent": ["AVA"], "type": ["D", "DF"]},
            "2024-01-01T00",
            "2024-01-01T02",
            page_size=4,
        )
    assert len(rows) == 6
    assert {row["type"] for row in rows} == {"D", "DF"}
    frame = to_frame(rows, REGION, REGION_URL)
    assert frame["value"].dtype == float
    assert {"_source", "_source_url", "_ingested_at"} <= set(frame.columns)


def test_failure_message_cannot_carry_the_api_key() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    with httpx.Client(transport=transport) as client, pytest.raises(EiaError) as caught:
        fetch_rows(client, REGION_URL, "secret-value", {}, "2024-01-01T00", "2024-01-01T02")
    assert "secret-value" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_months_cross_a_year_boundary() -> None:
    assert list(months(date(2023, 11, 15), date(2024, 2, 1))) == [
        (2023, 11),
        (2023, 12),
        (2024, 1),
        (2024, 2),
    ]


def test_month_window_stops_at_the_freeze() -> None:
    assert month_window(2024, 2, date(2026, 10, 31)) == ("2024-02-01T00", "2024-02-29T23")
    assert month_window(2026, 10, date(2026, 10, 15)) == ("2026-10-01T00", "2026-10-15T23")


@pytest.mark.vcr
def test_recent_pull_writes_one_file_apart_from_the_frozen_data(tmp_path: Path) -> None:
    lake = pafs.SubTreeFileSystem(str(tmp_path), pafs.LocalFileSystem())
    now = datetime(2026, 10, 31, 12, tzinfo=UTC)
    with httpx.Client(timeout=60) as client:
        rows = ingest_recent(
            ["PNM"], client, os.environ.get("EIA_API_KEY", "replay-only"), lake, now
        )
    frame = get_frame(lake, "raw/eia_recent/region_data/pulled=2026-10-31T12.parquet")
    assert len(frame) == rows > 0
    assert frame["period"].min() == "2026-10-28T12"
    assert frame["period"].max() == "2026-10-31T12"
    assert not (tmp_path / "raw" / "eia").exists()
