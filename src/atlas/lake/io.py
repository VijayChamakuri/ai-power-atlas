"""Raw and derived data live in the lake so a re-run reads the frozen snapshot, not today's web."""

import io

import pandas as pd
import pyarrow as pa
import pyarrow.fs as pafs
import pyarrow.parquet as pq

from atlas.config import Settings

BUCKET = "atlas-lake"


def open_lake(settings: Settings) -> pafs.FileSystem:
    s3 = pafs.S3FileSystem(
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        endpoint_override=settings.minio_endpoint,
        scheme="http",
        region="us-east-1",
    )
    return pafs.SubTreeFileSystem(BUCKET, s3)


def exists(lake: pafs.FileSystem, key: str) -> bool:
    return bool(lake.get_file_info(key).type != pafs.FileType.NotFound)


def put_bytes(lake: pafs.FileSystem, key: str, body: bytes) -> None:
    lake.create_dir(key.rsplit("/", 1)[0], recursive=True)
    with lake.open_output_stream(key) as stream:
        stream.write(body)


def get_bytes(lake: pafs.FileSystem, key: str) -> bytes:
    with lake.open_input_stream(key) as stream:
        return bytes(stream.read())


def put_frame(lake: pafs.FileSystem, key: str, frame: pd.DataFrame) -> None:
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), buffer)
    put_bytes(lake, key, buffer.getvalue())


def get_frame(lake: pafs.FileSystem, key: str) -> pd.DataFrame:
    return pq.read_table(io.BytesIO(get_bytes(lake, key))).to_pandas()
