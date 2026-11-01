-- The window ends at the BA's last hour with data, per Amendment 2 of docs/analysis_plan.md.
with

series_ends as (
    select
        ba,
        max(hour_utc) as series_end_utc
    from {{ ref('int_demand_cleaned') }}
    where value_mw is not null
    group by ba
),

in_window as (
    select
        demand.ba,
        demand.value_mw,
        demand.is_clean,
        series_ends.series_end_utc
    from {{ ref('int_demand_cleaned') }} as demand
    inner join series_ends on demand.ba = series_ends.ba
    where
        demand.value_mw is not null
        and demand.hour_utc
        >= cast(series_ends.series_end_utc as date) - {{ var('peak_window_days') }}
)

select
    ba,
    series_end_utc,
    max(value_mw) as raw_peak_mw,
    max(value_mw) filter (where is_clean) as peak_mw,
    count(*) filter (where not is_clean) as dropped_hours
from in_window
group by ba, series_end_utc
