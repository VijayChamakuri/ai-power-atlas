import hashlib
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pyarrow.fs as pafs

from atlas.ingest.files import FileSource, snapshot, snapshot_key
from atlas.lake.io import exists, get_frame, put_bytes, put_frame


def local_lake(tmp_path: Path) -> pafs.FileSystem:
    return pafs.SubTreeFileSystem(str(tmp_path), pafs.LocalFileSystem())


def test_frame_round_trip(tmp_path: Path) -> None:
    lake = local_lake(tmp_path)
    frame = pd.DataFrame({"site": ["a"], "power_mw": [1.5]})
    put_frame(lake, "derived/sites/sites.parquet", frame)
    assert get_frame(lake, "derived/sites/sites.parquet").equals(frame)


def test_snapshot_is_never_downloaded_twice(tmp_path: Path) -> None:
    lake = local_lake(tmp_path)
    source = FileSource("epoch", "data_centers.csv", "https://epoch.ai/x.csv")
    day = date(2026, 10, 31)
    put_bytes(lake, snapshot_key(source, day), b"frozen")

    def refuse(_: httpx.Request) -> httpx.Response:
        raise AssertionError("a frozen snapshot must not be fetched again")

    with httpx.Client(transport=httpx.MockTransport(refuse)) as client:
        key, sha256 = snapshot(source, day, lake, client)
    assert exists(lake, key)
    assert sha256 == hashlib.sha256(b"frozen").hexdigest()
