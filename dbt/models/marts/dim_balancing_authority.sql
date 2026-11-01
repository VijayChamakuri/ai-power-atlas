with

names as (
    select
        ba,
        max(ba_name) as ba_name
    from {{ ref('int_demand_cleaned') }}
    group by ba
)

select
    candidates.ba,
    names.ba_name,
    candidates.site_count,
    candidates.site_power_mw,
    candidates.first_site_date,
    candidates.peak_mw,
    candidates.dropped_hours,
    candidates.series_end_utc,
    candidates.share as site_share_of_peak,
    candidates.candidate,
    limits.test_dates,
    limits.mde_mw
from {{ ref('stg_candidates__bas') }} as candidates
left join names on candidates.ba = names.ba
left join {{ ref('fct_detectability') }} as limits on candidates.ba = limits.ba
