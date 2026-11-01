-- One row per site and candidate BA, with the go test written out in SQL.
with

candidates as (
    select ba
    from {{ ref('stg_candidates__bas') }}
    where candidate
),

joined as (
    select
        bridge.site,
        bridge.ba,
        bridge.overlap,
        sites.power_mw,
        sites.first_date,
        sites.behind_meter_risk,
        sites.confidence,
        limits.mde_mw
    from {{ ref('bridge_site_ba') }} as bridge
    inner join candidates on bridge.ba = candidates.ba
    inner join {{ ref('stg_sites__sites') }} as sites on bridge.site = sites.site
    left join {{ ref('fct_detectability') }} as limits on bridge.ba = limits.ba
)

select
    site,
    ba,
    power_mw,
    first_date,
    confidence,
    mde_mw,
    overlap,
    behind_meter_risk,
    power_mw / mde_mw as power_to_limit,
    coalesce(power_mw >= mde_mw, false) as above_limit,
    not behind_meter_risk and not overlap and mde_mw is not null as eligible,
    coalesce(not behind_meter_risk and not overlap and power_mw >= mde_mw, false) as passes_go,
    case
        when mde_mw is null then 'no limit available'
        when behind_meter_risk then 'on-site power flag'
        when overlap then 'overlapping BA areas'
        when power_mw < mde_mw then 'below limit'
        else 'passes'
    end as outcome
from joined
