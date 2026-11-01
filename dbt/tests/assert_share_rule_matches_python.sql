-- The candidate rule from docs/analysis_plan.md, restated in SQL.
select
    ba,
    candidate
from {{ ref('stg_candidates__bas') }}
where
    candidate
    <> coalesce(
        share >= {{ var('candidate_share') }}
        and cast(series_end_utc as date) >= first_site_date,
        false
    )
