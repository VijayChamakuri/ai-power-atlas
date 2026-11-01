import io
import tarfile
from pathlib import Path

import pyarrow.fs as pafs
import pytest

from atlas.lake.archive import export_lake, restore_lake
from atlas.lake.io import exists, get_bytes, put_bytes


def local_lake(path: Path) -> pafs.FileSystem:
    path.mkdir()
    return pafs.SubTreeFileSystem(str(path), pafs.LocalFileSystem())


def test_round_trip_keeps_every_byte(tmp_path: Path) -> None:
    source = local_lake(tmp_path / "source")
    put_bytes(source, "raw/files/epoch/a.csv", b"site,power\nx,1\n")
    put_bytes(source, "raw/eia/year=2024/b.parquet", b"\x00\x01binary")
    backup = tmp_path / "backup.tar.gz"
    assert export_lake(source, backup) == 2

    target = local_lake(tmp_path / "target")
    assert restore_lake(target, backup) == 2
    assert get_bytes(target, "raw/files/epoch/a.csv") == b"site,power\nx,1\n"
    assert get_bytes(target, "raw/eia/year=2024/b.parquet") == b"\x00\x01binary"


def test_damaged_backup_writes_nothing(tmp_path: Path) -> None:
    source = local_lake(tmp_path / "source")
    put_bytes(source, "raw/a.csv", b"real")
    backup = tmp_path / "backup.tar.gz"
    export_lake(source, backup)

    damaged = tmp_path / "damaged.tar.gz"
    with tarfile.open(backup, "r:gz") as old, tarfile.open(damaged, "w:gz") as new:
        for member in old.getmembers():
            handle = old.extractfile(member)
            body = handle.read() if handle else b""
            if member.name == "raw/a.csv":
                body = b"fake"
            new.addfile(member, io.BytesIO(body))

    target = local_lake(tmp_path / "target")
    with pytest.raises(ValueError, match="Hash mismatch"):
        restore_lake(target, damaged)
    assert not exists(target, "raw/a.csv")
