"""Site coordinates and BA codes. Only the codes are stored: the polygons are Esri-licensed."""

import csv
import io
import re
import statistics
import zipfile
from pathlib import Path
from typing import NamedTuple

import httpx
import pandas as pd
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = structlog.get_logger()

GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
BA_LAYER_URL = (
    "https://services8.arcgis.com/peDZJliSvYims39Q/arcgis/rest/services/"
    "Balancing_Authorities_Summary/FeatureServer/31/query"
)
EARTH_LINK = re.compile(r"earth\.google\.com/web/(?:search/[^@\s)]*/)?@(-?\d+\.\d+),(-?\d+\.\d+)")
SEEDS = Path(__file__).parents[3] / "dbt" / "seeds" / "site_locations.csv"


class ServiceBusyError(RuntimeError):
    """ArcGIS can answer a failed query with HTTP 200 and an error body instead of a status code."""


retry_transient = retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError, ServiceBusyError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(min=2, max=60),
    reraise=True,
)


class Point(NamedTuple):
    longitude: float
    latitude: float


def earth_point(text: str) -> Point | None:
    # The median ignores one link that points somewhere else on the map.
    points = [(float(lat), float(lon)) for lat, lon in EARTH_LINK.findall(text)]
    if not points:
        return None
    return Point(
        statistics.median(lon for _, lon in points), statistics.median(lat for lat, _ in points)
    )


def zip_point(address: str, centroids: dict[str, Point]) -> Point | None:
    # A leading five-digit token is a street number, even when it is also a real ZIP elsewhere.
    tokens = re.findall(r"\b\d{5}\b", re.sub(r"^\s*\d+(?:[-\u2013]\d+)?", "", address))
    matches = [token for token in tokens if token in centroids]
    return centroids[matches[-1]] if matches else None


def parse_zcta_centroids(archive: bytes) -> dict[str, Point]:
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        text = opened.read(opened.namelist()[0]).decode("utf-8")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    return {
        row["GEOID"]: Point(float(row["INTPTLONG"].strip()), float(row["INTPTLAT"]))
        for row in ({key.strip(): value for key, value in raw.items() if key} for raw in reader)
    }


@retry_transient
def geocode(client: httpx.Client, address: str) -> Point | None:
    response = client.get(
        GEOCODER_URL,
        params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
    )
    if response.status_code >= 500:
        response.raise_for_status()
    # The geocoder answers an address it cannot parse with an errors body and no result.
    matches = response.json().get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    coordinates = matches[0]["coordinates"]
    return Point(coordinates["x"], coordinates["y"])


@retry_transient
def lookup_bas(client: httpx.Client, point: Point) -> list[str]:
    response = client.get(
        BA_LAYER_URL,
        params={
            "geometry": f"{point.longitude},{point.latitude}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "balancing_authority_code",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    response.raise_for_status()
    body = response.json()
    if "features" not in body:
        raise ServiceBusyError(str(body.get("error", "response had no features")))
    return sorted(feature["attributes"]["balancing_authority_code"] for feature in body["features"])


def locate_site(
    site: pd.Series,
    client: httpx.Client,
    centroids: dict[str, Point],
    seeds: pd.DataFrame,
) -> tuple[Point | None, str, str]:
    """Order and sources come from Amendment 1 in docs/analysis_plan.md."""
    address = str(site["address"])
    point = geocode(client, address) if address else None
    if point:
        return point, "census_geocoder", GEOCODER_URL
    point = earth_point(str(site["location_text"]))
    if point:
        return point, "epoch_earth_link", "epoch_timeline_or_sources"
    point = zip_point(address, centroids)
    if point:
        return point, "zip_centroid", "census_gazetteer_zcta"
    seeded = seeds[seeds["site"] == site["site"]]
    if len(seeded):
        code = str(seeded["zip"].iloc[0]).zfill(5)
        return centroids[code], "hand_zip_centroid", str(seeded["source_url"].iloc[0])
    return None, "unlocated", ""


def map_sites(
    sites: pd.DataFrame, client: httpx.Client, centroids: dict[str, Point]
) -> pd.DataFrame:
    """A site with no power by the freeze cannot change a share, a date, or the go test."""
    seeds = pd.read_csv(SEEDS, dtype={"zip": str})
    rows = []
    for _, site in sites[sites["power_mw"] > 0].iterrows():
        point, method, source = locate_site(site, client, centroids, seeds)
        codes = lookup_bas(client, point) if point else []
        log.info("site_mapped", site=site["site"], method=method, bas=codes)
        rows.append(
            {
                "site": site["site"],
                "longitude": point.longitude if point else None,
                "latitude": point.latitude if point else None,
                "location_method": method,
                "location_source": source,
                "ba_codes": ",".join(codes),
            }
        )
    return pd.DataFrame(rows)
