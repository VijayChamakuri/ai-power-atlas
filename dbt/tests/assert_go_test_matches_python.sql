-- Every site and BA pair must exist on both sides with the same verdict, so the README's site
-- counts rest on two separate implementations of the go test.
select
    coalesce(marts.site, stored.site) as site,
    coalesce(marts.ba, stored.ba) as ba,
    marts.passes_go as sql_passes,
    stored.passes_go as python_passes,
    marts.eligible as sql_eligible,
    stored.eligible as python_eligible
from {{ ref('fct_site_detectability') }} as marts
full outer join {{ ref('stg_detectability__go_test') }} as stored
    on marts.site = stored.site and marts.ba = stored.ba
where
    marts.site is null
    or stored.site is null
    or marts.passes_go <> stored.passes_go
    or marts.eligible <> stored.eligible
