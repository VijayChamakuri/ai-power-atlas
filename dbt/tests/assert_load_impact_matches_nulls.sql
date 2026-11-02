-- The rank p and the 90% interval follow from the stored null windows alone, so SQL recomputes both.
with

nulls as (
    select
        impact.site_run,
        count(*) as windows,
        count(*) filter (where estimates.estimate_mw >= impact.estimate_mw) as at_or_above,
        quantile_cont(estimates.estimate_mw, 0.95) as q95,
        quantile_cont(estimates.estimate_mw, 0.05) as q05
    from {{ ref('fct_dc_load_impact') }} as impact
    inner join {{ ref('stg_detectability__estimates') }} as estimates on impact.ba = estimates.ba
    group by impact.site_run
)

select
    impact.site_run,
    impact.p,
    (1 + nulls.at_or_above) / (1 + nulls.windows) as sql_p
from {{ ref('fct_dc_load_impact') }} as impact
left join nulls on impact.site_run = nulls.site_run
where
    nulls.site_run is null
    or abs(impact.p - (1 + nulls.at_or_above) / (1 + nulls.windows)) > 1e-9
    or abs(impact.low_mw - (impact.estimate_mw - nulls.q95)) > 1e-6
    or abs(impact.high_mw - (impact.estimate_mw - nulls.q05)) > 1e-6
