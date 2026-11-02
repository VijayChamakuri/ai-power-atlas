-- Fields the early run leaves empty are typed here, because an all-null Parquet column has no type.
select
    site,
    ba,
    cast(start as date) as start_date,
    regexp_extract(filename, 'derived/(m2[a-z_]*)/', 1) as run,
    cast(regexp_extract(filename, 'freeze=([0-9-]+)/', 1) as date) as snapshot_freeze,
    cast(expected_mw as double) as expected_mw,
    cast(estimate_mw as double) as estimate_mw,
    cast(low_mw as double) as low_mw,
    cast(high_mw as double) as high_mw,
    cast(p as double) as p,
    cast(threshold_mw as double) as threshold_mw,
    cast(lead_mw as double) as lead_mw,
    cast(minus_90_mw as double) as minus_90_mw,
    cast(plus_90_mw as double) as plus_90_mw,
    cast(other_grid_p as double) as other_grid_p,
    cast(synthetic_gap_mw as double) as synthetic_gap_mw,
    cast(adjusted_p as double) as adjusted_p,
    cast(label as varchar) as label,
    cast(revision_mw as double) as revision_mw
from {{ source('derived', 'm2_results') }}
