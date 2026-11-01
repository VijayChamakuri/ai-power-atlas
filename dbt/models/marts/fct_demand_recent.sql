{{ config(tags=['recent']) }}

-- EIA revises recent hours, so the latest pull of each hour wins.
select
    ba,
    ba_name,
    series,
    value_mw,
    hour_utc,
    ingested_at
from {{ ref('stg_eia__recent') }}
qualify row_number() over (partition by ba, series, hour_utc order by ingested_at desc) = 1
