select
    ba,
    benchmark,
    mape,
    rmse,
    peak_hour_mae
from {{ ref('stg_detectability__scores') }}
