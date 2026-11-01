-- Bad hours stay in the table and are flagged, so the raw value is never lost.
with

demand as (
    select
        ba,
        ba_name,
        hour_utc,
        value_mw
    from {{ ref('stg_eia__region_data') }}
    where series = 'D'
    union all
    select
        ba,
        ba_name,
        hour_utc,
        value_mw
    from {{ ref('stg_eia__sub_ba') }}
),

medians as (
    select
        ba,
        median(value_mw) as median_mw
    from demand
    where value_mw > 0
    group by ba
)

select
    demand.ba,
    demand.ba_name,
    demand.hour_utc,
    demand.value_mw,
    coalesce(
        demand.value_mw > 0
        and demand.value_mw <= {{ var('bad_value_median_multiple') }} * medians.median_mw,
        false
    ) as is_clean
from demand
left join medians on demand.ba = medians.ba
