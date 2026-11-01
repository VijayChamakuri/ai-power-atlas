"""CI cannot reach MinIO, so dbt builds on a real slice of the frozen lake instead of made-up rows.

The slice holds the full raw history of the two BAs that pass the go test. Peaks need all of it,
because the median behind the bad-hour cutoff spans a BA's whole history, so the checks of SQL
against Python still run in CI. Other sources are cut down only to keep the repo small.
"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.fs as pafs
import pyarrow.parquet as pq

from atlas.config import FREEZE_DATE
from atlas.lake.io import get_frame

SAMPLE_BAS = ("IPCO", "PNM")  # The only two sites that pass are in these BAs.
SUB_BA_SAMPLE_MONTHS = 3  # Sub-BA data has no check that needs its whole history.
WEATHER_SAMPLE_DAYS = 90  # Enough to test the weighted join, at 1% of the size.
RECENT_SAMPLE_PULLS = 2  # Two overlapping pulls, so deduplication has something to do.


def _files(lake: pafs.FileSystem, prefix: str, suffix: str = ".parquet") -> list[str]:
    infos = lake.get_file_info(pafs.FileSelector(prefix, recursive=True))
    return sorted(info.path for info in infos if info.path.endswith(suffix))


def _write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path, compression="zstd")


def write_sample(lake: pafs.FileSystem, root: Path) -> None:
    keys = [
        key
        for key in _files(lake, "raw/eia/region_data")
        if any(key.endswith(f"respondent={ba}.parquet") for ba in SAMPLE_BAS)
    ]
    region = pd.concat([get_frame(lake, key) for key in keys], ignore_index=True)
    _write(region, root / "raw/eia/region_data/sample.parquet")

    sub_keys = _files(lake, "raw/eia/region_sub_ba_data")[-SUB_BA_SAMPLE_MONTHS:]
    sub_ba = pd.concat([get_frame(lake, key) for key in sub_keys], ignore_index=True)
    _write(sub_ba, root / "raw/eia/region_sub_ba_data/sample.parquet")

    for number, key in enumerate(_files(lake, "raw/eia_recent/region_data")[-RECENT_SAMPLE_PULLS:]):
        recent = get_frame(lake, key)
        kept = recent[recent["respondent"].isin(SAMPLE_BAS)]
        _write(kept, root / f"raw/eia_recent/region_data/pull_{number}.parquet")

    freeze = FREEZE_DATE.isoformat()
    counties = get_frame(lake, f"derived/candidates/freeze={freeze}/counties.parquet")
    for fips in sorted(set(counties[counties["ba"].isin(SAMPLE_BAS)]["fips"])):
        frame = get_frame(lake, f"raw/weather/county={fips}.parquet")
        _write(frame.tail(WEATHER_SAMPLE_DAYS * 24), root / f"raw/weather/county={fips}.parquet")

    for prefix in ("derived/sites", "derived/candidates", "derived/detectability"):
        for key in _files(lake, f"{prefix}/freeze={freeze}"):
            _write(get_frame(lake, key), root / key)
