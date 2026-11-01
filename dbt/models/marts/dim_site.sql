select
    sites.site,
    sites.power_mw,
    sites.first_date,
    sites.address,
    sites.behind_meter_risk,
    sites.behind_meter_terms,
    sites.confidence,
    locations.longitude,
    locations.latitude,
    locations.location_method,
    locations.location_source,
    locations.ba_codes
from {{ ref('stg_sites__sites') }} as sites
left join {{ ref('stg_sites__site_bas') }} as locations on sites.site = locations.site
