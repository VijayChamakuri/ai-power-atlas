"""Weather for the most populated counties in each BA, the weighting in docs/analysis_plan.md."""

import io
import zipfile
from datetime import UTC, date, datetime

import httpx
import pandas as pd
import pyarrow.fs as pafs
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from atlas.ingest.geo import Point, lookup_bas
from atlas.lake.io import exists, put_frame

log = structlog.get_logger()

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
TOP_COUNTIES = 10


def parse_counties(gazetteer_zip: bytes, population_csv: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(gazetteer_zip)) as opened:
        text = opened.read(opened.namelist()[0]).decode("utf-8")
    gazetteer = pd.read_csv(io.StringIO(text), sep="\t", dtype={"GEOID": str})
    gazetteer.columns = gazetteer.columns.str.strip()
    # The Census population file is Latin-1 because of Spanish county names in Puerto Rico.
    population = pd.read_csv(
        io.BytesIO(population_csv), encoding="latin-1", dtype={"STATE": str, "COUNTY": str}
    )
    population = population[population["SUMLEV"] == 50].assign(
        GEOID=lambda frame: frame["STATE"] + frame["COUNTY"]
    )
    merged = gazetteer.merge(population[["GEOID", "POPESTIMATE2025"]], on="GEOID")
    return (
        merged.rename(
            columns={
                "GEOID": "fips",
                "INTPTLAT": "latitude",
                "INTPTLONG": "longitude",
                "POPESTIMATE2025": "population",
            }
        )[["fips", "latitude", "longitude", "population"]]
        .sort_values("population", ascending=False)
        .reset_index(drop=True)
    )


def top_counties(
    counties: pd.DataFrame, candidates: list[str], client: httpx.Client
) -> pd.DataFrame:
    """Walks counties by population and stops early, to keep polygon lookups to what is needed."""
    needed = {ba: TOP_COUNTIES for ba in candidates}
    rows = []
    for county in counties.to_dict("records"):
        if not any(needed.values()):
            break
        for code in lookup_bas(client, Point(county["longitude"], county["latitude"])):
            if needed.get(code):
                needed[code] -= 1
                rows.append(
                    {
                        "ba": code,
                        "fips": county["fips"],
                        "latitude": county["latitude"],
                        "longitude": county["longitude"],
                        "population": county["population"],
                    }
                )
    log.info("counties_selected", short=[ba for ba, left in needed.items() if left])
    return pd.DataFrame(rows)


@retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(8),
    # Open-Meteo's free tier limits calls per minute, so waits must be able to outlast a minute.
    wait=wait_exponential(min=5, max=120),
    reraise=True,
)
def fetch_weather(
    client: httpx.Client, latitude: float, longitude: float, start: date, end: date
) -> pd.DataFrame:
    response = client.get(
        ARCHIVE_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": "temperature_2m,relative_humidity_2m",
            "temperature_unit": "fahrenheit",
            "timezone": "GMT",
        },
    )
    response.raise_for_status()
    return pd.DataFrame(response.json()["hourly"])


def ingest_county(
    fips: str,
    latitude: float,
    longitude: float,
    client: httpx.Client,
    lake: pafs.FileSystem,
    start: date,
    end: date,
) -> None:
    key = f"raw/weather/county={fips}.parquet"
    if exists(lake, key):
        return
    frame = fetch_weather(client, latitude, longitude, start, end)
    frame["_source"] = "open_meteo"
    frame["_source_url"] = ARCHIVE_URL
    frame["_ingested_at"] = datetime.now(UTC).isoformat()
    put_frame(lake, key, frame)
    log.info("weather_county", fips=fips, rows=len(frame))
