import io
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
import pyarrow.fs as pafs
import structlog
import typer

from atlas.config import FREEZE_DATE, HISTORY_START, Settings
from atlas.ingest.datacenters import apply_flag_seeds, build_sites
from atlas.ingest.eia import ingest_region, ingest_sub_ba
from atlas.ingest.files import FILE_SOURCES, snapshot, snapshot_key
from atlas.ingest.geo import SEEDS, map_sites, parse_zcta_centroids
from atlas.ingest.weather import ingest_county, parse_counties, top_counties
from atlas.lake.io import get_bytes, get_frame, open_lake, put_frame
from atlas.ml.candidates import peak_demand, select_candidates
from atlas.source_check import USER_AGENT, render_report, run_checks

log = structlog.get_logger()

app = typer.Typer(no_args_is_help=True)
sources_app = typer.Typer(no_args_is_help=True)
ingest_app = typer.Typer(no_args_is_help=True)
app.add_typer(sources_app, name="sources")
app.add_typer(ingest_app, name="ingest")

SITES_KEY = f"derived/sites/freeze={FREEZE_DATE.isoformat()}/sites.parquet"
SITE_BAS_KEY = f"derived/sites/freeze={FREEZE_DATE.isoformat()}/site_bas.parquet"
CANDIDATES_KEY = f"derived/candidates/freeze={FREEZE_DATE.isoformat()}/candidates.parquet"
COUNTIES_KEY = f"derived/candidates/freeze={FREEZE_DATE.isoformat()}/counties.parquet"


@app.callback()
def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ]
    )


@sources_app.command("check")
def sources_check(output: Path = Path("docs/source_status.md")) -> None:
    """Exits 1 unless every source returned records or a page, because M0 gates on that."""
    results = run_checks(Settings())
    output.write_text(render_report(results, datetime.now(UTC)))
    if any(result.status not in ("ok", "page_only") for result in results):
        raise typer.Exit(code=1)


def _client() -> httpx.Client:
    return httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def _read_snapshot_csv(lake_body: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(lake_body))


@ingest_app.command("files")
def ingest_files() -> None:
    """Snapshots are keyed by the freeze date, so a later run cannot change M1's inputs."""
    lake = open_lake(Settings())
    with _client() as client:
        for source in FILE_SOURCES:
            snapshot(source, FREEZE_DATE, lake, client)


@ingest_app.command("sites")
def ingest_sites() -> None:
    """Needs `ingest files` first, because it reads only the frozen snapshots."""
    lake = open_lake(Settings())
    by_name = {source.name: snapshot_key(source, FREEZE_DATE) for source in FILE_SOURCES}
    sites = apply_flag_seeds(
        build_sites(
            _read_snapshot_csv(get_bytes(lake, by_name["data_centers.csv"])),
            _read_snapshot_csv(get_bytes(lake, by_name["data_center_timelines.csv"])),
            FREEZE_DATE,
        ),
        pd.read_csv(SEEDS.parent / "site_flags.csv"),
    )
    put_frame(lake, SITES_KEY, sites)
    centroids = parse_zcta_centroids(get_bytes(lake, by_name["zcta.zip"]))
    with _client() as client:
        put_frame(lake, SITE_BAS_KEY, map_sites(sites, client, centroids))


@ingest_app.command("eia")
def ingest_eia(resume: bool = True) -> None:
    """Pulls every BA that holds a powered site, since selection needs each one's peak."""
    settings = Settings()
    lake = open_lake(settings)
    site_bas = get_frame(lake, SITE_BAS_KEY)
    codes = sorted({code for row in site_bas["ba_codes"] for code in row.split(",") if code})
    with _client() as client:
        for code in codes:
            ingest_region(
                code, client, settings.eia_api_key, lake, HISTORY_START, FREEZE_DATE, resume
            )
        # Secondary analysis in docs/analysis_plan.md, included whatever its share.
        ingest_sub_ba(
            "PJM", "AEP", client, settings.eia_api_key, lake, HISTORY_START, FREEZE_DATE, resume
        )


def _read_demand(lake: pafs.FileSystem, ba: str) -> pd.DataFrame:
    selector = pafs.FileSelector("raw/eia/region_data", recursive=True)
    keys = [
        info.path
        for info in lake.get_file_info(selector)
        if info.path.endswith(f"respondent={ba}.parquet")
    ]
    frame = pd.concat([get_frame(lake, key) for key in keys], ignore_index=True)
    return frame[frame["type"] == "D"].sort_values("period").reset_index(drop=True)


@ingest_app.command("candidates")
def ingest_candidates() -> None:
    """Reads only each BA's peak, so selection cannot depend on any model result."""
    lake = open_lake(Settings())
    site_bas = get_frame(lake, SITE_BAS_KEY)
    codes = sorted({code for row in site_bas["ba_codes"] for code in row.split(",") if code})
    peaks = []
    for ba in codes:
        peak, raw_peak, dropped, series_end = peak_demand(_read_demand(lake, ba), FREEZE_DATE)
        peaks.append(
            {
                "ba": ba,
                "peak_mw": peak,
                "raw_peak_mw": raw_peak,
                "dropped_hours": dropped,
                "series_end": series_end,
            }
        )
    table = select_candidates(get_frame(lake, SITES_KEY), site_bas, pd.DataFrame(peaks))
    put_frame(lake, CANDIDATES_KEY, table)
    log.info("candidates_selected", candidates=table[table["candidate"]]["ba"].tolist())


@ingest_app.command("weather")
def ingest_weather() -> None:
    """Needs `ingest candidates` first, because weather is pulled only for candidate BAs."""
    lake = open_lake(Settings())
    table = get_frame(lake, CANDIDATES_KEY)
    # The AEP zone is in the plan's secondary analysis, and its weather comes from PJM's counties.
    bas = sorted(set(table[table["candidate"]]["ba"]) | {"PJM"})
    by_name = {source.name: snapshot_key(source, FREEZE_DATE) for source in FILE_SOURCES}
    counties = parse_counties(
        get_bytes(lake, by_name["counties.zip"]),
        get_bytes(lake, by_name["co-est2025-alldata.csv"]),
    )
    with _client() as client:
        chosen = top_counties(counties, bas, client)
        put_frame(lake, COUNTIES_KEY, chosen)
        for county in chosen.drop_duplicates("fips").to_dict("records"):
            ingest_county(
                county["fips"],
                county["latitude"],
                county["longitude"],
                client,
                lake,
                HISTORY_START,
                FREEZE_DATE,
            )
