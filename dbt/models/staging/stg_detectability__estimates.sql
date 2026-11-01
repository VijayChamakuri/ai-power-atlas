select
    ba,
    "order" as test_date_order,
    estimate_mw
from {{ source('derived', 'estimates') }}
