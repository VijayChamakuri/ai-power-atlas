select
    site,
    power_mw,
    address,
    behind_meter_risk,
    behind_meter_terms,
    confidence,
    cast(first_date as date) as first_date
from {{ source('derived', 'sites') }}
