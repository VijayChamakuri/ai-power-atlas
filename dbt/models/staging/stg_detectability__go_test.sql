select
    site,
    ba,
    power_mw,
    overlap,
    mde_mw,
    implied_utilization,
    above_mde,
    eligible,
    passes_go
from {{ source('derived', 'go_test') }}
