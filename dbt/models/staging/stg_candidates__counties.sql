select
    ba,
    fips,
    latitude,
    longitude,
    population
from {{ source('derived', 'counties') }}
