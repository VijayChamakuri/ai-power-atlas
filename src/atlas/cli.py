import io
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import mlflow
import pandas as pd
import pyarrow.fs as pafs
import structlog
import typer

from atlas.config import (
    BA_TIMEZONES,
    EIA_AGGREGATES,
    FREEZE_DATE,
    HISTORY_START,
    LIGHTGBM_PARAMS,
    M2_DONOR_MIN_COVERAGE,
    M2_DONOR_MIN_MEDIAN_MW,
    M2_EARLY_FREEZE_DATE,
    M2_EARLY_SITE,
    M2_FREEZE_DATE,
    M2_LEAD_DAYS,
    M2_PRIMARY,
    M2_SECONDARY,
    M2_SHIFT_DAYS,
    PEAK_WINDOW_DAYS,
    POST_DAYS,
    TRAIN_GAP_DAYS,
    Settings,
)
from atlas.ingest.datacenters import apply_flag_seeds, build_sites
from atlas.ingest.eia import ingest_recent, ingest_region, ingest_sub_ba, list_respondents
from atlas.ingest.files import FILE_SOURCES, snapshot, snapshot_key
from atlas.ingest.geo import SEEDS, map_sites, parse_zcta_centroids
from atlas.ingest.weather import ingest_county, parse_counties, top_counties
from atlas.lake.archive import export_lake, restore_lake
from atlas.lake.io import exists, get_bytes, get_frame, open_lake, put_bytes, put_frame
from atlas.lake.sample import write_sample
from atlas.ml import figures
from atlas.ml.baseline import fit_predict
from atlas.ml.candidates import clean_demand, peak_demand, select_candidates
from atlas.ml.detectability import (
    BaResult,
    analyze_ba,
    daily_residuals,
    go_test,
    minimum_detectable,
    pseudo_dates,
    step_estimate,
    verdict,
)
from atlas.ml.event_study import (
    SiteResult,
    daily_errors,
    keep_early_result,
    peak_of,
    qualifies_as_donor,
    render_early_result,
    render_event_study,
    require_early_unlocked,
    require_first_run,
    require_unlocked,
    result_from_frame,
    result_to_frame,
    score_site,
    with_labels,
)
from atlas.ml.features import build_features, to_utc_index, weighted_weather
from atlas.ml.paper import build_pdf
from atlas.ml.report import render_results
from atlas.source_check import USER_AGENT, render_report, run_checks

log = structlog.get_logger()

app = typer.Typer(no_args_is_help=True)
sources_app = typer.Typer(no_args_is_help=True)
ingest_app = typer.Typer(no_args_is_help=True)
app.add_typer(sources_app, name="sources")
analyze_app = typer.Typer(no_args_is_help=True)
lake_app = typer.Typer(no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")
app.add_typer(lake_app, name="lake")
app.add_typer(analyze_app, name="analyze")

SITES_KEY = f"derived/sites/freeze={FREEZE_DATE.isoformat()}/sites.parquet"
SITE_BAS_KEY = f"derived/sites/freeze={FREEZE_DATE.isoformat()}/site_bas.parquet"
CANDIDATES_KEY = f"derived/candidates/freeze={FREEZE_DATE.isoformat()}/candidates.parquet"
RESULTS_KEY = f"derived/detectability/freeze={FREEZE_DATE.isoformat()}/sites.parquet"
SCORES_KEY = f"derived/detectability/freeze={FREEZE_DATE.isoformat()}/scores.parquet"
ESTIMATES_KEY = f"derived/detectability/freeze={FREEZE_DATE.isoformat()}/estimates.parquet"
COUNTIES_KEY = f"derived/candidates/freeze={FREEZE_DATE.isoformat()}/counties.parquet"


@dataclass(frozen=True)
class Snapshot:
    """Lake locations of one M2 snapshot, so the early run never reads the later one."""

    freeze: date
    root: str

    @property
    def raw_eia(self) -> str:
        return f"raw/{self.root}/freeze={self.freeze.isoformat()}/eia"

    @property
    def raw_weather(self) -> str:
        return f"raw/{self.root}/freeze={self.freeze.isoformat()}/weather"

    def derived(self, name: str) -> str:
        return f"derived/{self.root}/freeze={self.freeze.isoformat()}/{name}"


M2_SNAPSHOT = Snapshot(M2_FREEZE_DATE, "m2")
M2_EARLY_SNAPSHOT = Snapshot(M2_EARLY_FREEZE_DATE, "m2_early")
M2_EARLY_RESULT_KEY = M2_EARLY_SNAPSHOT.derived("result.parquet")


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


@lake_app.command("export")
def lake_export(path: Path) -> None:
    """Writes the whole lake to one file with a hash for every entry."""
    log.info("lake_exported", path=str(path), files=export_lake(open_lake(Settings()), path))


@lake_app.command("restore")
def lake_restore(path: Path) -> None:
    """Refuses a damaged backup before writing anything."""
    log.info("lake_restored", path=str(path), files=restore_lake(open_lake(Settings()), path))


@lake_app.command("sample")
def lake_sample(root: Path) -> None:
    """Rewrites the real slice that dbt builds on in CI."""
    write_sample(open_lake(Settings()), root)
    log.info("lake_sampled", root=str(root))


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


@ingest_app.command("eia-recent")
def ingest_eia_recent() -> None:
    """The hourly DAG's pull. It covers candidate BAs, the only ones the study follows."""
    settings = Settings()
    lake = open_lake(settings)
    table = get_frame(lake, CANDIDATES_KEY)
    respondents = sorted(table[table["candidate"]]["ba"])
    with _client() as client:
        ingest_recent(respondents, client, settings.eia_api_key, lake, datetime.now(UTC))


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


def _read_series(
    lake: pafs.FileSystem, ba: str, prefix: str = "raw/eia"
) -> tuple[pd.Series, pd.Series]:
    if ba == "AEP":
        selector = pafs.FileSelector(f"{prefix}/region_sub_ba_data", recursive=True)
        keys = [
            i.path for i in lake.get_file_info(selector) if i.path.endswith("subba=AEP.parquet")
        ]
        frame = pd.concat([get_frame(lake, key) for key in keys], ignore_index=True)
        frame = frame.assign(type="D")
    else:
        selector = pafs.FileSelector(f"{prefix}/region_data", recursive=True)
        keys = [
            i.path
            for i in lake.get_file_info(selector)
            if i.path.endswith(f"respondent={ba}.parquet")
        ]
        frame = pd.concat([get_frame(lake, key) for key in keys], ignore_index=True)
    frame = frame.set_index(to_utc_index(frame["period"])).sort_index()
    forecast = frame[frame["type"] == "DF"]["value"]
    return frame[frame["type"] == "D"]["value"], forecast


def _features_for(
    lake: pafs.FileSystem, ba: str, counties: pd.DataFrame, prefix: str = "raw/weather"
) -> pd.DataFrame:
    # The AEP zone has no polygon of its own, so it uses PJM's counties. docs/analysis_plan.md
    # lists this as a limitation of the secondary analysis.
    chosen = counties[counties["ba"] == ("PJM" if ba == "AEP" else ba)]
    frames = {f: get_frame(lake, f"{prefix}/county={f}.parquet") for f in chosen["fips"]}
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
    put_frame(
        lake,
        SCORES_KEY,
        pd.DataFrame(
            [
                {"ba": r.ba, "benchmark": name, **values}
                for r in results.values()
                for name, values in r.scores.items()
            ]
        ),
    )
    output.write_text(
        render_results(results, candidates, table, sites, seed, commit, verdict(table))
    )


@analyze_app.command("figures")
def analyze_figures(output: Path = Path("docs/figures")) -> None:
    """Refits one window for the worked example, ending before that BA's first listed site."""
    settings = Settings()
    lake = open_lake(settings)
    by_name = {source.name: snapshot_key(source, FREEZE_DATE) for source in FILE_SOURCES}
    with _client() as client:
        snapshot(
            next(s for s in FILE_SOURCES if s.source == "census_states"), FREEZE_DATE, lake, client
        )
    candidates = get_frame(lake, CANDIDATES_KEY)
    counties = get_frame(lake, COUNTIES_KEY)
    sites = get_frame(lake, SITES_KEY)
    site_bas = get_frame(lake, SITE_BAS_KEY)
    table = get_frame(lake, RESULTS_KEY)
    estimates = get_frame(lake, ESTIMATES_KEY)
    scores = get_frame(lake, SCORES_KEY)
    seed = pd.read_csv(SEEDS.parent / "sub_ba_sites.csv")
    output.mkdir(parents=True, exist_ok=True)

    first_sites = {
        str(row["ba"]): date.fromisoformat(str(row["first_site_date"]))
        for row in candidates.to_dict("records")
    }
    first_sites["AEP"] = date.fromisoformat(
        str(sites[sites["site"].isin(seed["site"])]["first_date"].dropna().min())
    )

    aep, _ = _read_series(lake, "AEP")
    limits = table.drop_duplicates("ba")[["ba", "mde_mw"]].merge(
        candidates[["ba", "peak_mw"]], on="ba"
    )
    aep_values = estimates[estimates["ba"] == "AEP"]["estimate_mw"].to_numpy()
    window_start = pd.Timestamp(FREEZE_DATE, tz="UTC") - pd.Timedelta(days=PEAK_WINDOW_DAYS)
    aep_clean = clean_demand(aep.dropna())
    aep_row = {
        "ba": "AEP",
        "mde_mw": minimum_detectable(aep_values),
        "peak_mw": float(aep_clean[aep_clean.index >= window_start].max()),
    }
    limits = pd.concat([limits, pd.DataFrame([aep_row])], ignore_index=True)

    dated = []
    demand_by_ba = {}
    for ba in limits.dropna(subset=["mde_mw"])["ba"]:
        demand, _ = _read_series(lake, ba)
        demand_by_ba[ba] = demand
        dates = pseudo_dates(HISTORY_START, first_sites[ba], demand.dropna().index.max().date())
        chosen = estimates[estimates["ba"] == ba].sort_values("order")
        dated.append(chosen.assign(date=pd.to_datetime(dates)))
    series = pd.concat(dated, ignore_index=True)

    figures.site_map(
        figures.site_status(table, sites, site_bas),
        get_bytes(lake, by_name["cb_2023_us_state_20m.zip"]),
        output / "fig1_site_map.png",
    )

    anatomy = []
    for ba in ("IPCO", "PJM"):
        cutoff = pd.Timestamp(first_sites[ba], tz="UTC")
        before_site = clean_demand(demand_by_ba[ba].dropna())
        anatomy.append(
            {
                "ba": ba,
                "demand": before_site[before_site.index < cutoff],
                "temperature": _features_for(lake, ba, counties)["temperature_f"],
                "timezone": BA_TIMEZONES[ba],
            }
        )
    figures.demand_anatomy(anatomy, output / "fig2_demand_anatomy.png")

    ba = "IPCO"
    features = _features_for(lake, ba, counties)
    cleaned = clean_demand(demand_by_ba[ba].dropna()).rename("demand")
    frame = features.join(cleaned, how="inner").dropna()
    worked = series[series["ba"] == ba].sort_values("order")
    t = worked["date"].iloc[-1].date()
    moment = pd.Timestamp(t, tz="UTC")
    train_end = moment - pd.Timedelta(days=TRAIN_GAP_DAYS)
    future = frame[
        (frame.index >= train_end) & (frame.index < moment + pd.Timedelta(days=POST_DAYS))
    ]
    predicted = fit_predict(frame[frame.index < train_end], future)
    estimate = step_estimate(daily_residuals(future["demand"], predicted), t)
    figures.worked_example(
        ba, future["demand"], predicted, t, worked, output / "fig3_worked_example.png"
    )
    figures.noise_panels(series, limits, first_sites, output / "fig5_noise_panels.png")
    figures.power_curves(estimates, limits, table, output / "fig7_power_curves.png")
    figures.forest_plot(table, estimates, output / "fig6_forest_plot.png")
    figures.grid_context(limits, candidates, output / "fig4_grid_context.png")
    figures.accuracy(scores, limits, output / "fig8_accuracy.png")
    log.info(
        "figures_written",
        path=str(output),
        check_estimate=estimate,
        stored=float(worked["estimate_mw"].iloc[-1]),
    )


@analyze_app.command("paper")
def analyze_paper(output: Path = Path("docs/paper.pdf")) -> None:
    """Needs Google Chrome, which turns the HTML version of the README into a PDF."""
    build_pdf(Path("README.md"), Path("logs/paper.html"), output)
    log.info("paper_written", path=str(output), bytes=output.stat().st_size)


def _take_snapshot(snapshot: Snapshot, targets: list[str], include_aep: bool) -> None:
    settings = Settings()
    lake = open_lake(settings)
    site_bas = get_frame(lake, SITE_BAS_KEY)
    site_codes = {code for row in site_bas["ba_codes"] for code in row.split(",") if code}
    by_name = {source.name: snapshot_key(source, FREEZE_DATE) for source in FILE_SOURCES}
    counties = parse_counties(
        get_bytes(lake, by_name["counties.zip"]),
        get_bytes(lake, by_name["co-est2025-alldata.csv"]),
    )
    with _client() as client:
        respondents = list_respondents(client, settings.eia_api_key)
        possible = [
            code
            for code in respondents
            if code not in EIA_AGGREGATES and code not in site_codes and code in BA_TIMEZONES
        ]
        for code in sorted({*targets, *possible}):
            ingest_region(
                code,
                client,
                settings.eia_api_key,
                lake,
                HISTORY_START,
                snapshot.freeze,
                prefix=snapshot.raw_eia,
            )
        if include_aep:
            ingest_sub_ba(
                "PJM",
                "AEP",
                client,
                settings.eia_api_key,
                lake,
                HISTORY_START,
                snapshot.freeze,
                prefix=snapshot.raw_eia,
            )
        donors = []
        for code in possible:
            try:
                demand, _ = _read_series(lake, code, snapshot.raw_eia)
            except ValueError:
                continue
            if qualifies_as_donor(
                demand,
                HISTORY_START,
                snapshot.freeze,
                M2_DONOR_MIN_MEDIAN_MW,
                M2_DONOR_MIN_COVERAGE,
            ):
                donors.append(code)
        chosen = top_counties(counties, [*targets, *donors], client)
        donors = [code for code in donors if code in set(chosen["ba"])]
        put_frame(lake, snapshot.derived("donors.parquet"), pd.DataFrame({"ba": donors}))
        put_frame(lake, snapshot.derived("counties.parquet"), chosen)
        for county in chosen.drop_duplicates("fips").to_dict("records"):
            ingest_county(
                county["fips"],
                county["latitude"],
                county["longitude"],
                client,
                lake,
                HISTORY_START,
                snapshot.freeze,
                prefix=snapshot.raw_weather,
            )
    put_bytes(lake, snapshot.derived("complete"), b"done")
    log.info("m2_snapshot_complete", root=snapshot.root, donors=donors)


@ingest_app.command("m2")
def ingest_m2() -> None:
    """Takes the M2 snapshot once. Weather is rate limited, so this can take days and can resume."""
    require_unlocked(date.today())
    targets = sorted({str(item["ba"]) for item in (*M2_PRIMARY, *M2_SECONDARY)} - {"AEP"})
    _take_snapshot(M2_SNAPSHOT, targets, include_aep=True)


def _early_item() -> dict[str, Any]:
    return next(dict(item) for item in M2_PRIMARY if item["site"] == M2_EARLY_SITE)


@ingest_app.command("m2-early")
def ingest_m2_early() -> None:
    """Amendment 5's snapshot: the early site's grid and the control grids, nothing else."""
    require_early_unlocked(M2_EARLY_SITE, date.today())
    _take_snapshot(M2_EARLY_SNAPSHOT, [str(_early_item()["ba"])], include_aep=False)


def _require_complete(lake: pafs.FileSystem, snapshot: Snapshot) -> None:
    """A partial pool would change the placebo, so no estimate exists until the pull finishes."""
    if not exists(lake, snapshot.derived("complete")):
        raise typer.BadParameter(f"The {snapshot.root} snapshot has not finished.")


def _m2_errors(
    lake: pafs.FileSystem, ba: str, counties: pd.DataFrame, t: date, snapshot: Snapshot
) -> pd.Series:
    demand, _ = _read_series(lake, ba, snapshot.raw_eia)
    return daily_errors(demand, _features_for(lake, ba, counties, snapshot.raw_weather), t)


def _m2_site(
    lake: pafs.FileSystem,
    item: dict[str, Any],
    counties: pd.DataFrame,
    donors: list[str],
    nulls: pd.DataFrame,
    snapshot: Snapshot,
    include_plus: bool = True,
) -> SiteResult:
    ba, t = str(item["ba"]), item["start"]
    offsets = [("main", 0), ("lead", -M2_LEAD_DAYS), ("minus", -M2_SHIFT_DAYS)]
    if include_plus:
        offsets.append(("plus", M2_SHIFT_DAYS))
    errors = {
        name: _m2_errors(lake, ba, counties, t + timedelta(days=offset), snapshot)
        for name, offset in offsets
    }
    demand, _ = _read_series(lake, ba, snapshot.raw_eia)
    donor_errors = {code: _m2_errors(lake, code, counties, t, snapshot) for code in donors}
    donor_peaks = {
        code: peak_of(_read_series(lake, code, snapshot.raw_eia)[0], snapshot.freeze)
        for code in donors
    }
    return score_site(
        str(item["site"]),
        ba,
        t,
        float(str(item["expected_mw"])),
        errors,
        nulls[nulls["ba"] == ba].sort_values("order")["estimate_mw"].to_numpy(),
        peak_of(demand, snapshot.freeze),
        donor_errors,
        donor_peaks,
    )


@analyze_app.command("event-study")
def analyze_event_study(output: Path = Path("docs/m2_event_study.md")) -> None:
    """Runs once on the M2 snapshot. Amendment 4 fixes every rule, including the labels."""
    require_unlocked(date.today())
    lake = open_lake(Settings())
    _require_complete(lake, M2_SNAPSHOT)
    counties = get_frame(lake, M2_SNAPSHOT.derived("counties.parquet"))
    donors = get_frame(lake, M2_SNAPSHOT.derived("donors.parquet"))["ba"].tolist()
    nulls = get_frame(lake, ESTIMATES_KEY)
    primary = []
    for item in M2_PRIMARY:
        result = _m2_site(lake, dict(item), counties, donors, nulls, M2_SNAPSHOT)
        if item["site"] == M2_EARLY_SITE and exists(lake, M2_EARLY_RESULT_KEY):
            early = result_from_frame(get_frame(lake, M2_EARLY_RESULT_KEY))
            result = keep_early_result(early, result)
        primary.append(result)
    secondary = [
        _m2_site(lake, dict(item), counties, donors, nulls, M2_SNAPSHOT) for item in M2_SECONDARY
    ]
    output.write_text(render_event_study(with_labels(primary), secondary, len(donors)))


@analyze_app.command("event-study-early")
def analyze_event_study_early(output: Path = Path("docs/m2_early_los_lunas.md")) -> None:
    """Runs once, under Amendment 5. The stored result stops a second run for a better answer."""
    require_early_unlocked(M2_EARLY_SITE, date.today())
    lake = open_lake(Settings())
    require_first_run(exists(lake, M2_EARLY_RESULT_KEY))
    _require_complete(lake, M2_EARLY_SNAPSHOT)
    counties = get_frame(lake, M2_EARLY_SNAPSHOT.derived("counties.parquet"))
    donors = get_frame(lake, M2_EARLY_SNAPSHOT.derived("donors.parquet"))["ba"].tolist()
    nulls = get_frame(lake, ESTIMATES_KEY)
    result = _m2_site(
        lake, _early_item(), counties, donors, nulls, M2_EARLY_SNAPSHOT, include_plus=False
    )
    put_frame(lake, M2_EARLY_RESULT_KEY, result_to_frame(result))
    output.write_text(render_early_result(result, len(donors)))
