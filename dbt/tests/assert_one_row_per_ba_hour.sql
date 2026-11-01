-- A second row for an hour would double count demand in anything built on this table.
select
    ba,
    hour_utc,
    count(*) as row_count
from {{ ref('fct_demand_hourly') }}
group by ba, hour_utc
having count(*) > 1
