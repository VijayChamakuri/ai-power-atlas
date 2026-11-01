"""Probe every source in docs/PLAN.md section 7 before any ingest code depends on it.

A landing page answering 200 only proves the host is up, so those rows say `page_only`
and never claim a row count. Only `ok` means real records came back.
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
import structlog

from atlas.config import Settings

log = structlog.get_logger()

Status = Literal["ok", "page_only", "needs_key", "blocked", "rate_limited", "unreachable"]
Facts = tuple[str | None, int | None]

USER_AGENT = "atlas-source-check/0.1 (+public data reachability probe)"
TIMEOUT_SECONDS = 60.0
# Marion County, Indiana. The probes only need one real county.
PROBE_LATITUDE = 39.77
PROBE_LONGITUDE = -86.16
PROBE_FIPS = "18097"
OVERPASS_QUERY = (
    '[out:json][timeout:25];nwr["telecom"="data_center"](39.6,-86.4,40.0,-85.9);out count;'
)
EIA_SORT = {"length": "1", "sort[0][column]": "period", "sort[0][direction]": "desc"}


def parse_eia(response: httpx.Response) -> Facts:
    body: dict[str, Any] = response.json()["response"]
    return body["data"][0]["period"], int(body["total"])


def parse_csv_rows(date_column: str | None = None) -> Callable[[httpx.Response], Facts]:
    def parse(response: httpx.Response) -> Facts:
        rows = list(csv.DictReader(io.StringIO(response.text)))
        if not rows:
            raise ValueError("CSV has a header but no rows")
        if date_column is None:
            return None, len(rows)
        dates = [row[date_column] for row in rows if row[date_column]]
        return (max(dates) if dates else None), len(rows)

    return parse


def parse_open_meteo(response: httpx.Response) -> Facts:
    times: list[str] = response.json()["hourly"]["time"]
    return times[-1], len(times)


def parse_overpass(response: httpx.Response) -> Facts:
    body: dict[str, Any] = response.json()
    return body["osm3s"]["timestamp_osm_base"], int(body["elements"][0]["tags"]["total"])


def parse_sec(response: httpx.Response) -> Facts:
    facts: list[dict[str, Any]] = response.json()["units"]["USD"]
    return max(fact["filed"] for fact in facts), len(facts)


def parse_miso(response: httpx.Response) -> Facts:
    return response.json()["LoadInfo"]["RefId"], None


def parse_arcgis_count(response: httpx.Response) -> Facts:
    return None, len(response.json()["features"])


def parse_census(response: httpx.Response) -> Facts:
    return None, len(response.json()) - 1


@dataclass(frozen=True)
class Source:
    key: str
    plan_row: int
    url: str
    parse: Callable[[httpx.Response], Facts] | None = None
    params: dict[str, str] = field(default_factory=dict)
    post_query: str | None = None
    secret_param: str | None = None
    required_setting: str | None = None
    note: str = ""


def _eia(key: str, plan_row: int, route: str, frequency: str) -> Source:
    return Source(
        key=key,
        plan_row=plan_row,
        url=f"https://api.eia.gov/v2/electricity/{route}/data/",
        parse=parse_eia,
        params={"frequency": frequency, **EIA_SORT},
        secret_param="api_key",
        required_setting="eia_api_key",
    )


def build_sources(today: datetime) -> list[Source]:
    # The weather archive lags real time by days, and drought maps come out weekly.
    weather_end = (today - timedelta(days=7)).date().isoformat()
    weather_start = (today - timedelta(days=8)).date().isoformat()
    drought_end = today.strftime("%m/%d/%Y")
    drought_start = (today - timedelta(days=28)).strftime("%m/%d/%Y")
    browser_note = "Blocks scripted requests. Plan a manual download into raw/files/."
    return [
        _eia("eia_930_region", 1, "rto/region-data", "hourly"),
        _eia("eia_930_fuel_type", 1, "rto/fuel-type-data", "hourly"),
        _eia("eia_930_interchange", 1, "rto/interchange-data", "hourly"),
        _eia("eia_930_sub_ba", 1, "rto/region-sub-ba-data", "hourly"),
        Source(
            "epoch_data_centers",
            2,
            "https://epoch.ai/data/data_centers/data_centers.csv",
            parse_csv_rows(),
        ),
        Source(
            "epoch_timelines",
            2,
            "https://epoch.ai/data/data_centers/data_center_timelines.csv",
            parse_csv_rows("Date"),
            note="Replaces gpu_clusters.csv, now 404. Future dates are Epoch's own projections.",
        ),
        Source("lbnl_queued_up", 3, "https://emp.lbl.gov/queues", note=browser_note),
        Source("epa_egrid", 4, "https://www.epa.gov/egrid"),
        _eia("eia_923_facility_fuel", 5, "facility-fuel", "monthly"),
        _eia("eia_860_capacity", 5, "operating-generator-capacity", "monthly"),
        Source(
            "iso_miso",
            6,
            "https://public-api.misoenergy.org/api/RealTimeTotalLoad",
            parse_miso,
        ),
        Source("iso_pjm", 6, "https://dataminer2.pjm.com/list"),
        Source(
            "iso_ercot",
            6,
            "https://www.ercot.com/content/cdr/html/real_time_system_conditions.html",
        ),
        Source("iso_spp", 6, "https://portal.spp.org/"),
        Source(
            "open_meteo",
            7,
            "https://archive-api.open-meteo.com/v1/archive",
            parse_open_meteo,
            params={
                "latitude": str(PROBE_LATITUDE),
                "longitude": str(PROBE_LONGITUDE),
                "start_date": weather_start,
                "end_date": weather_end,
                "hourly": "temperature_2m",
            },
        ),
        _eia("eia_retail_sales", 8, "retail-sales", "monthly"),
        Source("wri_aqueduct", 9, "https://www.wri.org/aqueduct"),
        Source(
            "us_drought_monitor",
            10,
            "https://usdmdataservices.unl.edu/api/CountyStatistics/"
            "GetDroughtSeverityStatisticsByAreaPercent",
            parse_csv_rows("MapDate"),
            params={
                "aoi": PROBE_FIPS,
                "startdate": drought_start,
                "enddate": drought_end,
                "statisticsType": "1",
            },
        ),
        Source(
            "fcc_broadband", 11, "https://broadbandmap.fcc.gov/data-download", note=browser_note
        ),
        Source("census_tiger", 12, "https://www2.census.gov/geo/tiger/"),
        Source(
            "census_population",
            12,
            "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/"
            "co-est2025-alldata.csv",
            parse_csv_rows(),
            note="County population without a key, for weighting BA temperature.",
        ),
        Source(
            "census_acs",
            12,
            "https://api.census.gov/data/2023/acs/acs5",
            parse_census,
            params={"get": "NAME,B01001_001E", "for": "state:18"},
            secret_param="key",
            required_setting="census_api_key",
        ),
        Source(
            "ba_territories",
            13,
            "https://services8.arcgis.com/peDZJliSvYims39Q/arcgis/rest/services/"
            "Balancing_Authorities_Summary/FeatureServer/31/query",
            parse_arcgis_count,
            params={
                "where": "1=1",
                "outFields": "balancing_authority_code",
                "returnGeometry": "false",
                "f": "json",
            },
            note="Replaces HIFLD. Esri license, so lookups only.",
        ),
        Source(
            "sec_edgar",
            14,
            "https://data.sec.gov/api/xbrl/companyconcept/CIK0000789019/us-gaap/"
            "PaymentsToAcquirePropertyPlantAndEquipment.json",
            parse_sec,
            required_setting="sec_contact_email",
        ),
        Source(
            "osm_overpass",
            15,
            "https://overpass-api.de/api/interpreter",
            parse_overpass,
            post_query=OVERPASS_QUERY,
        ),
    ]


@dataclass(frozen=True)
class Result:
    source: Source
    status: Status
    last_updated: str | None = None
    row_count: int | None = None
    detail: str = ""


def probe(source: Source, client: httpx.Client, settings: Settings) -> Result:
    secret = getattr(settings, source.required_setting) if source.required_setting else ""
    if source.required_setting and not secret:
        return Result(source, "needs_key", detail=f"Set {source.required_setting.upper()} in .env")

    params = dict(source.params)
    headers: dict[str, str] = {}
    if source.secret_param:
        params[source.secret_param] = secret
    elif source.required_setting:
        # SEC rejects requests that do not name a contact in the User-Agent.
        headers["User-Agent"] = f"AI Power Atlas {secret}"

    try:
        if source.post_query:
            response = client.post(source.url, data={"data": source.post_query}, headers=headers)
        else:
            response = client.get(source.url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        # The exception text can hold the request URL, which can hold the API key.
        return Result(source, "unreachable", detail=type(exc).__name__)

    if response.status_code in (401, 403):
        if source.secret_param:
            return Result(source, "needs_key", detail=f"Key rejected: HTTP {response.status_code}")
        return Result(source, "blocked", detail=f"HTTP {response.status_code}")
    if response.status_code == 429:
        return Result(source, "rate_limited", detail="HTTP 429")
    if response.status_code != 200:
        return Result(source, "unreachable", detail=f"HTTP {response.status_code}")
    if source.secret_param and "<title>Invalid Key</title>" in response.text:
        # Census answers a rejected key with HTTP 200 and an HTML page.
        return Result(source, "needs_key", detail="Key rejected. Activate it or request a new one.")
    if source.parse is None:
        return Result(source, "page_only", response.headers.get("last-modified"))

    try:
        last_updated, row_count = source.parse(response)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return Result(source, "unreachable", detail=f"Unexpected body: {type(exc).__name__}")
    return Result(source, "ok", last_updated, row_count)


def run_checks(settings: Settings, today: datetime | None = None) -> list[Result]:
    now = today or datetime.now(UTC)
    results = []
    with httpx.Client(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for source in build_sources(now):
            result = probe(source, client, settings)
            log.info(
                "source_probed", source=source.key, status=result.status, rows=result.row_count
            )
            results.append(result)
    return results


def render_report(results: list[Result], checked_at: datetime) -> str:
    lines = [
        "# Source status",
        "",
        f"Generated by `atlas sources check` at {checked_at:%Y-%m-%d %H:%M} UTC.",
        "",
        "`row_count` is what the probe returned or the API reported. Probes for weather, drought,",
        "Overpass, SEC, and ACS cover one small sample, not the full dataset.",
        "",
        "`Latest date` is the newest date in the data, or Last-Modified for `page_only` rows.",
        "It can be in the future: EIA region data holds day-ahead forecasts.",
        "",
        "| Plan row | Source | Status | Latest date | Row count | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        notes = " ".join(part for part in (result.detail, result.source.note) if part)
        rows = "" if result.row_count is None else f"{result.row_count:,}"
        lines.append(
            f"| {result.source.plan_row} | [{result.source.key}]({result.source.url}) "
            f"| {result.status} | {result.last_updated or ''} | {rows} | {notes} |"
        )
    return "\n".join(lines) + "\n"
