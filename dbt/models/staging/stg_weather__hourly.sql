select
    regexp_extract(filename, 'county=(\d+)\.parquet', 1) as fips,
    temperature_2m as temperature_f,
    relative_humidity_2m as humidity_pct,
    strptime(time, '%Y-%m-%dT%H:%M') as hour_utc,
    _source,
    _source_url,
    cast(_ingested_at as timestamp) as ingested_at
from {{ source('weather', 'hourly') }}
