"""One verified file holds the frozen lake, so losing a laptop cannot lose the M1 inputs."""

import hashlib
import io
import tarfile
from pathlib import Path

import pyarrow.fs as pafs

from atlas.lake.io import get_bytes, put_bytes

MANIFEST = "MANIFEST.sha256"
ATTRIBUTION = "ATTRIBUTION.txt"
ATTRIBUTION_TEXT = """Frozen inputs of AI Power Atlas M1, taken 2026-10-31.

EIA-930: U.S. Energy Information Administration. Public domain.
Frontier Data Centers: Epoch AI. CC BY 4.0. https://epoch.ai/data/data-centers-documentation
Weather data by Open-Meteo.com. CC BY 4.0.
Census files: US Census Bureau. Public domain.
derived/ holds BA codes looked up from Esri's Balancing_Authorities_Summary layer. The polygons are
not included, because they are under the Esri Master License Agreement.
"""


def _add(archive: tarfile.TarFile, name: str, body: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(body)
    archive.addfile(info, io.BytesIO(body))


def export_lake(lake: pafs.FileSystem, path: Path) -> int:
    selector = pafs.FileSelector("", recursive=True)
    files = sorted(
        info.path for info in lake.get_file_info(selector) if info.type == pafs.FileType.File
    )
    lines = []
    with tarfile.open(path, "w:gz") as archive:
        for key in files:
            body = get_bytes(lake, key)
            lines.append(f"{hashlib.sha256(body).hexdigest()}  {key}\n")
            _add(archive, key, body)
        _add(archive, MANIFEST, "".join(lines).encode())
        _add(archive, ATTRIBUTION, ATTRIBUTION_TEXT.encode())
    return len(files)


def restore_lake(lake: pafs.FileSystem, path: Path) -> int:
    """Checks every hash before writing anything, so a damaged backup cannot half-restore."""
    with tarfile.open(path, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        extracted = archive.extractfile(members[MANIFEST])
        if extracted is None:
            raise ValueError("Backup has an unreadable manifest")
        checked: dict[str, bytes] = {}
        for line in extracted.read().decode().splitlines():
            expected, key = line.split("  ", 1)
            if key.startswith("/") or ".." in key.split("/"):
                raise ValueError(f"Unsafe path in backup: {key}")
            handle = archive.extractfile(members[key])
            body = handle.read() if handle else b""
            if hashlib.sha256(body).hexdigest() != expected:
                raise ValueError(f"Hash mismatch in backup: {key}")
            checked[key] = body
    for key, body in checked.items():
        put_bytes(lake, key, body)
    return len(checked)
