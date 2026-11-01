select
    ba,
    benchmark,
    mape,
    rmse,
    peak_hour_mae
from {{ source('derived', 'scores') }}
