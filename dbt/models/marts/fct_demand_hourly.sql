-- Observed data only. Model residuals are not here, so this table cannot reveal the M2 result
-- before the freeze date in Amendment 4.
with

forecasts as (
    select
        ba,
        hour_utc,
        value_mw as eia_forecast_mw
    from {{ ref('stg_eia__region_data') }}
    where series = 'DF'
)

select
    demand.ba,
    demand.hour_utc,
    demand.value_mw as demand_mw,
    demand.is_clean,
    forecasts.eia_forecast_mw,
    weather.temperature_f,
    weather.humidity_pct
from {{ ref('int_demand_cleaned') }} as demand
left join forecasts on demand.ba = forecasts.ba and demand.hour_utc = forecasts.hour_utc
left join {{ ref('int_ba_weather') }} as weather
    on demand.ba = weather.ba and demand.hour_utc = weather.hour_utc
