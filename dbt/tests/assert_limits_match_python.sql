-- The limit in SQL comes from the stored estimates. It must equal what the go test used.
select distinct
    limits.ba,
    limits.mde_mw as sql_limit,
    stored.mde_mw as python_limit
from {{ ref('fct_detectability') }} as limits
inner join {{ ref('stg_detectability__go_test') }} as stored on limits.ba = stored.ba
where
    (limits.mde_mw is null) <> (stored.mde_mw is null)
    or abs(limits.mde_mw - stored.mde_mw) > 1e-6
union all
-- An empty join would otherwise pass this test without checking anything.
select
    null as ba,
    null as sql_limit,
    null as python_limit
where not exists (
    select 1
    from {{ ref('fct_detectability') }} as limits
    inner join {{ ref('stg_detectability__go_test') }} as stored on limits.ba = stored.ba
)
