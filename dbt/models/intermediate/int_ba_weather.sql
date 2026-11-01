-- Same weights as atlas.ml.features.weighted_weather. The AEP zone has no polygon of its own, so
-- it uses PJM's counties, a limitation docs/analysis_plan.md records.
with

counties as (
    select
        ba,
        fips,
        population * 1.0 / sum(population) over (partition by ba) as weight
    from {{ ref('stg_candidates__counties') }}
),

weighted as (
    select
        counties.ba,
        weather.hour_utc,
        sum(weather.temperature_f * counties.weight) as temperature_f,
        sum(weather.humidity_pct * counties.weight) as humidity_pct
    from counties
    inner join {{ ref('stg_weather__hourly') }} as weather on counties.fips = weather.fips
    group by counties.ba, weather.hour_utc
)

select * from weighted
union all
select
    'AEP' as ba,
    hour_utc,
    temperature_f,
    humidity_pct
from weighted
where ba = 'PJM'
