"""Fail loudly if Epoch renames a column: site power and dates decide the M1 gate."""

import pandera.pandas as pa

DATA_CENTERS = pa.DataFrameSchema(
    {
        "Name": pa.Column(str, unique=True),
        "Country": pa.Column(str),
        "Address": pa.Column(str, nullable=True),
        "Selected Sources": pa.Column(str, nullable=True),
    }
)

TIMELINES = pa.DataFrameSchema(
    {
        "Data center": pa.Column(str),
        "Date": pa.Column(str, pa.Check.str_matches(r"^\d{4}-\d{2}-\d{2}$")),
        "Construction status": pa.Column(str, nullable=True),
        "Power (MW)": pa.Column(float, pa.Check.ge(0)),
        "IT power (MW)": pa.Column(float, pa.Check.ge(0)),
    }
)
