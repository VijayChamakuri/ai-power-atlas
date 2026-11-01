select
    subba as ba,
    "subba-name" as ba_name,
    parent as parent_ba,
    'D' as series,
    value as value_mw,
    strptime(period, '%Y-%m-%dT%H') as hour_utc,
    _source,
    _source_url,
    cast(_ingested_at as timestamp) as ingested_at
from {{ source('eia', 'region_sub_ba_data') }}
