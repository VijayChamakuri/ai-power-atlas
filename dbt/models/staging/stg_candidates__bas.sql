select
    ba,
    site_power_mw,
    site_count,
    peak_mw,
    raw_peak_mw,
    dropped_hours,
    share,
    candidate,
    cast(first_site_date as date) as first_site_date,
    strptime(series_end, '%Y-%m-%dT%H') as series_end_utc
from {{ source('derived', 'candidates') }}
