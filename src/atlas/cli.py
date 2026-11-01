import io
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import mlflow
import pandas as pd
import pyarrow.fs as pafs
import structlog
import typer

from atlas.config import BA_TIMEZONES, FREEZE_DATE, HISTORY_START, LIGHTGBM_PARAMS, Settings
from atlas.ingest.datacenters import apply_flag_seeds, build_sites
from atlas.ingest.eia import ingest_region, ingest_sub_ba
from atlas.ingest.files import FILE_SOURCES, snapshot, snapshot_key
from atlas.ingest.geo import SEEDS, map_sites, parse_zcta_centroids
from atlas.ingest.weather import ingest_county, parse_counties, top_counties
from atlas.lake.io import get_bytes, get_frame, open_lake, put_frame
from atlas.ml.candidates import peak_demand, select_candidates
from atlas.ml.detectability import BaResult, analyze_ba, go_test, verdict
from atlas.ml.features import build_features, to_utc_index, weighted_weather
from atlas.ml.report import render_results
from atlas.source_check import USER_AGENT, render_report, run_checks

log = structlog.get_logger()

app = typer.Typer(no_args_is_help=True)
sources_app = typer.Typer(no_args_is_help=True)
ingest_app = typer.Typer(no_args_is_help=True)
app.add_typer(sources_app, name="sources")
analyze_app = typer.Typer(no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")
app.add_typer(analyze_app, name="analyze")

SITES_KEY = f"derived/sites/freeze={FREEZE_DATE.isoformat()}/sites.parquet"
SITE_BAS_KEY = f"derived/sites/freeze={FREEZE_DATE.isoformat()}/site_bas.parquet"
CANDIDATES_KEY = f"derived/candidates/freeze={FREEZE_DATE.isoformat()}/candidates.parquet"
RESULTS_KEY = f"derived/detectability/freeze={FREEZE_DATE.isoformat()}/sites.parquet"
ESTIMATES_KEY = f"derived/detectability/freeze={FREEZE_DATE.isoformat()}/estimates.parquet"
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


def _read_series(lake: pafs.FileSystem, ba: str) -> tuple[pd.Series, pd.Series]:
    if ba == "AEP":
        selector = pafs.FileSelector("raw/eia/region_sub_ba_data", recursive=True)
        keys = [
            i.path for i in lake.get_file_info(selector) if i.path.endswith("subba=AEP.parquet")
        ]
        frame = pd.concat([get_frame(lake, key) for key in keys], ignore_index=True)
        frame = frame.assign(type="D")
    else:
        selector = pafs.FileSelector("raw/eia/region_data", recursive=True)
        keys = [
            i.path
            for i in lake.get_file_info(selector)
            if i.path.endswith(f"respondent={ba}.parquet")
        ]
        frame = pd.concat([get_frame(lake, key) for key in keys], ignore_index=True)
    frame = frame.set_index(to_utc_index(frame["period"])).sort_index()
    forecast = frame[frame["type"] == "DF"]["value"]
    return frame[frame["type"] == "D"]["value"], forecast


def _features_for(lake: pafs.FileSystem, ba: str, counties: pd.DataFrame) -> pd.DataFrame:
    # The AEP zone has no polygon of its own, so it uses PJM's counties. docs/analysis_plan.md
    # lists this as a limitation of the secondary analysis.
    chosen = counties[counties["ba"] == ("PJM" if ba == "AEP" else ba)]
    frames = {f: get_frame(lake, f"raw/weather/county={f}.parquet") for f in chosen["fips"]}
    populations = dict(zip(chosen["fips"], chosen["population"].astype(float), strict=True))
    return build_features(weighted_weather(frames, populations), BA_TIMEZONES[ba])


def _log_run(result: BaResult, first_site: date, commit: str) -> None:
    with mlflow.start_run(run_name=result.ba):
        mlflow.set_tags({"git_commit": commit, "status": result.status})
        mlflow.log_params(
            {
                **LIGHTGBM_PARAMS,
                "ba": result.ba,
                "first_site": str(first_site),
                "dates": result.dates,
            }
        )
        if result.mde_mw is None:
            return
        mlflow.log_metric("mde_mw", result.mde_mw)
        for name, scores in result.scores.items():
            mlflow.log_metrics({f"{name}_{key}": value for key, value in scores.items()})


@analyze_app.command("detectability")
def analyze_detectability(output: Path = Path("docs/m1_detectability.md")) -> None:
    """Runs only the BAs the candidate rule chose, plus the AEP zone as the secondary analysis."""
    settings = Settings()
    lake = open_lake(settings)
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment("m1-detectability")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    candidates = get_frame(lake, CANDIDATES_KEY)
    counties = get_frame(lake, COUNTIES_KEY)
    sites = get_frame(lake, SITES_KEY)
    site_bas = get_frame(lake, SITE_BAS_KEY)
    chosen = candidates[candidates["candidate"]]
    seed = pd.read_csv(SEEDS.parent / "sub_ba_sites.csv")
    aep_first = sites[sites["site"].isin(seed["site"])]["first_date"].dropna().min()
    plan = [(row["ba"], row["first_site_date"]) for row in chosen.to_dict("records")]
    plan.append(("AEP", aep_first))

    results = {}
    for ba, first in plan:
        demand, forecast = _read_series(lake, ba)
        first_site = date.fromisoformat(first)
        series_end = demand.dropna().index.max().date()
        result = analyze_ba(
            ba,
            demand,
            forecast,
            _features_for(lake, ba, counties),
            HISTORY_START,
            first_site,
            series_end,
        )
        results[ba] = result
        _log_run(result, first_site, commit)
        log.info(
            "ba_analyzed", ba=ba, status=result.status, dates=result.dates, mde_mw=result.mde_mw
        )

    bas = pd.DataFrame(
        [{"ba": r.ba, "mde_mw": r.mde_mw} for r in results.values() if r.ba != "AEP"]
    )
    table = go_test(sites, site_bas, bas)
    put_frame(lake, RESULTS_KEY, table.drop(columns=["location_text"]))
    put_frame(
        lake,
        ESTIMATES_KEY,
        pd.DataFrame(
            [
                {"ba": r.ba, "order": order, "estimate_mw": value}
                for r in results.values()
                for order, value in enumerate(r.estimates)
            ]
        ),
    )
    output.write_text(
        render_results(results, candidates, table, sites, seed, commit, verdict(table))
    )
