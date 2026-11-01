{{ config(tags=['recent']) }}

select
    respondent as ba,
    "respondent-name" as ba_name,
    type as series,
    value as value_mw,
    strptime(period, '%Y-%m-%dT%H') as hour_utc,
    _source,
    _source_url,
    cast(_ingested_at as timestamp) as ingested_at
from {{ source('eia', 'recent') }}
