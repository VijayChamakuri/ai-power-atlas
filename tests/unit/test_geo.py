import io
import zipfile

import httpx
import pytest

from atlas.ingest import geo
from atlas.ingest.geo import Point, earth_point, parse_zcta_centroids, zip_point

CENTROIDS = {"68138": Point(-96.1, 41.1), "14651": Point(-77.6, 43.1)}


def test_earth_point_reads_plain_and_search_links() -> None:
    text = (
        "[image](https://earth.google.com/web/@33.35450568,-111.67805903,407a,35y) "
        "[other](https://earth.google.com/web/search/Berwick,+PA/@33.36,-111.68,756a)"
    )
    point = earth_point(text)
    assert point == Point((-111.67805903 - 111.68) / 2, (33.35450568 + 33.36) / 2)


def test_earth_point_is_none_without_a_link() -> None:
    assert earth_point("Satellite imagery shows progress.") is None


def test_zip_point_skips_a_street_number_shaped_like_a_zip() -> None:
    address = "14651-15249 Gold Coast Rd 68138 Papillion Nebraska, USA"
    assert zip_point(address, CENTROIDS) == CENTROIDS["68138"]


def test_leading_street_number_is_not_a_zip() -> None:
    # Epoch's AWS New Albany address. 13360 is a real ZIP in New York.
    assert zip_point("13360 Miller Rd NW", {"13360": Point(-75.2, 43.4)}) is None


def test_zip_point_is_none_without_a_known_zip() -> None:
    assert zip_point("3500 River Rd, The Dalles, OR", CENTROIDS) is None


def test_parses_gazetteer_with_padded_header() -> None:
    # Header and spacing copied from the 2024 Census ZCTA Gazetteer file.
    text = (
        "GEOID\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG                   \n"
        "00601\t166836392\t798613\t64.416\t0.308\t18.180555\t-66.749961                   \n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("2024_Gaz_zcta_national.txt", text)
    assert parse_zcta_centroids(buffer.getvalue()) == {"00601": Point(-66.749961, 18.180555)}


def test_error_body_with_status_200_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    # Shape of the failure seen from Esri's layer during a full pipeline run on 2026-11-01.
    answers = [
        httpx.Response(200, json={"error": {"code": 400, "message": "Unable to complete"}}),
        httpx.Response(
            200, json={"features": [{"attributes": {"balancing_authority_code": "PJM"}}]}
        ),
    ]
    monkeypatch.setattr(geo.lookup_bas.retry, "sleep", lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(lambda _: answers.pop(0))) as client:
        assert geo.lookup_bas(client, Point(-86.5, 41.6)) == ["PJM"]
