{{ config(tags=['recent']) }}

-- Each hour appears in many overlapping pulls. Only the latest revision may survive.
select
    ba,
    series,
    hour_utc,
    count(*) as row_count
from {{ ref('fct_demand_recent') }}
group by ba, series, hour_utc
having count(*) > 1
