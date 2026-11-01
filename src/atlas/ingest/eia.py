"""One parquet file per BA and month, so a re-run replaces whole months and can resume."""

import calendar
from collections.abc import Iterator
from datetime import UTC, date, datetime

import httpx
import pandas as pd
import pandera.pandas as pa
import pyarrow.fs as pafs
import structlog

from atlas.contracts.eia import REGION, SUB_BA
from atlas.ingest.geo import retry_transient
from atlas.lake.io import exists, put_frame

log = structlog.get_logger()

BASE_URL = "https://api.eia.gov/v2/electricity/rto"
REGION_URL = f"{BASE_URL}/region-data/data/"
SUB_BA_URL = f"{BASE_URL}/region-sub-ba-data/data/"
PAGE_SIZE = 5000  # The most rows EIA v2 returns in one response.


class EiaError(RuntimeError):
    """Carries no URL: httpx errors include the query string, which holds the API key."""


def list_respondents(client: httpx.Client, api_key: str) -> list[str]:
    try:
        response = client.get(
            f"{BASE_URL}/region-data/facet/respondent", params={"api_key": api_key}
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EiaError(f"EIA request failed: {type(exc).__name__}") from None
    return sorted(item["id"] for item in response.json()["response"]["facets"])


def months(start: date, end: date) -> Iterator[tuple[int, int]]:
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def month_window(year: int, month: int, freeze: date) -> tuple[str, str]:
    last_day = min(date(year, month, calendar.monthrange(year, month)[1]), freeze)
    return f"{year}-{month:02}-01T00", f"{last_day.isoformat()}T23"


@retry_transient
def _get_page(client: httpx.Client, url: str, params: dict[str, str | int]) -> dict[str, object]:
    response = client.get(url, params=params)
    response.raise_for_status()
    body: dict[str, object] = response.json()["response"]
    return body


def fetch_rows(
    client: httpx.Client,
    url: str,
    api_key: str,
    facets: dict[str, list[str]],
    start: str,
    end: str,
    page_size: int = PAGE_SIZE,
) -> list[dict[str, object]]:
    params: dict[str, str | int] = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "start": start,
        "end": end,
        # A fixed order keeps rows from moving between pages while paging by offset.
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "sort[1][column]": "subba" if url == SUB_BA_URL else "type",
        "sort[1][direction]": "asc",
        "length": page_size,
    }
    for name, values in facets.items():
        for index, value in enumerate(values):
            params[f"facets[{name}][{index}]"] = value

    rows: list[dict[str, object]] = []
    while True:
        try:
            page = _get_page(client, url, {**params, "offset": len(rows)})
        except httpx.HTTPError as exc:
            raise EiaError(f"EIA request failed: {type(exc).__name__}") from None
        data = page["data"]
        assert isinstance(data, list)
        rows.extend(data)
        if not data or len(rows) >= int(str(page["total"])):
            return rows


def to_frame(rows: list[dict[str, object]], schema: pa.DataFrameSchema, url: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows).rename(columns={"value-units": "value_units"})
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce").astype(float)
    schema.validate(frame)
    frame["_source"] = "eia_930"
    frame["_source_url"] = url
    frame["_ingested_at"] = datetime.now(UTC).isoformat()
    return frame


def ingest_region(
    respondent: str,
    client: httpx.Client,
    api_key: str,
    lake: pafs.FileSystem,
    start: date,
    freeze: date,
    resume: bool = True,
    prefix: str = "raw/eia",
) -> int:
    total = 0
    for year, month in months(start, freeze):
        key = f"{prefix}/region_data/year={year}/month={month:02}/respondent={respondent}.parquet"
        if resume and exists(lake, key):
            continue
        window = month_window(year, month, freeze)
        rows = fetch_rows(
            client,
            REGION_URL,
            api_key,
            {"respondent": [respondent], "type": ["D", "DF"]},
            *window,
        )
        if rows:
            put_frame(lake, key, to_frame(rows, REGION, REGION_URL))
        total += len(rows)
        log.info("eia_month", respondent=respondent, year=year, month=month, rows=len(rows))
    return total


def ingest_sub_ba(
    parent: str,
    subba: str,
    client: httpx.Client,
    api_key: str,
    lake: pafs.FileSystem,
    start: date,
    freeze: date,
    resume: bool = True,
    prefix: str = "raw/eia",
) -> int:
    total = 0
    for year, month in months(start, freeze):
        key = (
            f"{prefix}/region_sub_ba_data/year={year}/month={month:02}/"
            f"parent={parent}/subba={subba}.parquet"
        )
        if resume and exists(lake, key):
            continue
        window = month_window(year, month, freeze)
        rows = fetch_rows(
            client, SUB_BA_URL, api_key, {"parent": [parent], "subba": [subba]}, *window
        )
        if rows:
            put_frame(lake, key, to_frame(rows, SUB_BA, SUB_BA_URL))
        total += len(rows)
        log.info("eia_sub_ba_month", subba=subba, year=year, month=month, rows=len(rows))
    return total
