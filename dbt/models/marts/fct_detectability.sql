-- Recomputes each BA's limit from the stored null estimates, so the SQL checks the Python result.
with

estimates as (
    select
        ba,
        count(*) as test_dates,
        quantile_cont(estimate_mw, {{ var('null_quantile') }}) as threshold_mw,
        quantile_cont(estimate_mw, {{ var('power_quantile') }}) as power_point_mw
    from {{ ref('stg_detectability__estimates') }}
    group by ba
)

select
    estimates.ba,
    estimates.test_dates,
    estimates.threshold_mw,
    case
        when estimates.test_dates >= {{ var('min_pseudo_dates') }}
            then estimates.threshold_mw - estimates.power_point_mw
    end as mde_mw,
    case
        when estimates.test_dates >= {{ var('min_pseudo_dates') }}
            then (estimates.threshold_mw - estimates.power_point_mw) / peaks.peak_mw
    end as mde_share_of_peak
from estimates
left join {{ ref('int_ba_peaks') }} as peaks on estimates.ba = peaks.ba
