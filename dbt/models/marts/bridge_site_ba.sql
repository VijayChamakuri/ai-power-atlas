-- A site inside overlapping BA polygons gets one row per BA, per Amendment 1.
select
    site,
    trim(ba) as ba,
    contains(ba_codes, ',') as overlap
from {{ ref('stg_sites__site_bas') }}, unnest(string_split(ba_codes, ',')) as codes (ba)
where trim(ba) <> ''
