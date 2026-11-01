"""Raw EIA rows keep bad values on purpose: the analysis plan drops them later and counts them."""

import pandera.pandas as pa

REGION = pa.DataFrameSchema(
    {
        "period": pa.Column(str, pa.Check.str_matches(r"^\d{4}-\d{2}-\d{2}T\d{2}$")),
        "respondent": pa.Column(str),
        "type": pa.Column(str, pa.Check.isin(["D", "DF"])),
        "value": pa.Column(float, nullable=True),
    }
)

SUB_BA = pa.DataFrameSchema(
    {
        "period": pa.Column(str, pa.Check.str_matches(r"^\d{4}-\d{2}-\d{2}T\d{2}$")),
        "parent": pa.Column(str),
        "subba": pa.Column(str),
        "value": pa.Column(float, nullable=True),
    }
)
