select
    site,
    longitude,
    latitude,
    location_method,
    location_source,
    ba_codes
from {{ source('derived', 'site_bas') }}
