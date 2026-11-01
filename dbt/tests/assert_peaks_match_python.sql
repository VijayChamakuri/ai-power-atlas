-- SQL and Python compute each BA's 12-month peak separately, so a drift in either one fails here.
select
    peaks.ba,
    peaks.peak_mw as sql_peak,
    stored.peak_mw as python_peak,
    peaks.raw_peak_mw as sql_raw_peak,
    stored.raw_peak_mw as python_raw_peak,
    peaks.dropped_hours as sql_dropped,
    stored.dropped_hours as python_dropped
from {{ ref('int_ba_peaks') }} as peaks
inner join {{ ref('stg_candidates__bas') }} as stored on peaks.ba = stored.ba
where
    abs(peaks.peak_mw - stored.peak_mw) > 1e-6
    or abs(peaks.raw_peak_mw - stored.raw_peak_mw) > 1e-6
    or peaks.dropped_hours <> stored.dropped_hours
    or peaks.series_end_utc <> stored.series_end_utc
union all
-- An empty join would otherwise pass this test without checking anything.
select
    null as ba,
    null as sql_peak,
    null as python_peak,
    null as sql_raw_peak,
    null as python_raw_peak,
    null as sql_dropped,
    null as python_dropped
where not exists (
    select 1
    from {{ ref('int_ba_peaks') }} as peaks
    inner join {{ ref('stg_candidates__bas') }} as stored on peaks.ba = stored.ba
)
