"""Keep each source file exactly as downloaded, so parsing bugs never need a new download."""

import hashlib
from dataclasses import dataclass
from datetime import date

import httpx
import pyarrow.fs as pafs
import structlog

from atlas.lake.io import exists, get_bytes, put_bytes

log = structlog.get_logger()

GAZETTEER = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer"


@dataclass(frozen=True)
class FileSource:
    source: str
    name: str
    url: str


FILE_SOURCES = [
    FileSource("epoch", "data_centers.csv", "https://epoch.ai/data/data_centers/data_centers.csv"),
    FileSource(
        "epoch",
        "data_center_timelines.csv",
        "https://epoch.ai/data/data_centers/data_center_timelines.csv",
    ),
    FileSource(
        "census_states",
        "cb_2023_us_state_20m.zip",
        "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_20m.zip",
    ),
    FileSource("census_zcta", "zcta.zip", f"{GAZETTEER}/2024_Gaz_zcta_national.zip"),
    FileSource("census_counties", "counties.zip", f"{GAZETTEER}/2024_Gaz_counties_national.zip"),
    FileSource(
        "census_population",
        "co-est2025-alldata.csv",
        "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/"
        "co-est2025-alldata.csv",
    ),
]


def snapshot_key(source: FileSource, day: date) -> str:
    return f"raw/files/{source.source}/{day.isoformat()}/{source.name}"


def snapshot(
    source: FileSource, day: date, lake: pafs.FileSystem, client: httpx.Client
) -> tuple[str, str]:
    """A snapshot is never replaced: the analysis plan freezes inputs at the first ingest."""
    key = snapshot_key(source, day)
    if exists(lake, key):
        body = get_bytes(lake, key)
    else:
        response = client.get(source.url)
        response.raise_for_status()
        body = response.content
        put_bytes(lake, key, body)
    sha256 = hashlib.sha256(body).hexdigest()
    log.info("file_snapshot", key=key, bytes=len(body), sha256=sha256)
    return key, sha256
