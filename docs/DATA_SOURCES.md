# Data sources

This file covers the sources M1 uses. All were pulled on 2026-10-31 unless noted, and
[source_status.md](source_status.md) has the status of the wider list in the build plan. No raw data
is committed, apart from small test fixtures cut from real responses.

## EIA-930 Hourly Grid Monitor

- URL: `https://api.eia.gov/v2/electricity/rto/region-data/data/` and `.../region-sub-ba-data/data/`
- License: public domain (US government).
- Attribution: U.S. Energy Information Administration, Hourly Electric Grid Monitor.
- Refresh: hourly. Needs a free key.
- Use: demand (`D`) and day-ahead forecast (`DF`) for 21 BAs, and demand for PJM's AEP zone, from
  2019-01-01 to the freeze.
- Known issues: recent hours get revised, and series have gaps, negative values, and spikes. WACM has
  no demand after 2026-04-02. Raw values stay in the lake, and bad hours are dropped and counted later.

## Epoch AI Frontier Data Centers

- URL: `https://epoch.ai/data/data_centers/data_centers.csv` and `.../data_center_timelines.csv`
- License: [CC BY 4.0](https://epoch.ai/llms.txt).
- Attribution: Epoch AI, "Frontier Data Centers". Retrieved from
  <https://epoch.ai/data/data-centers-documentation> on 2026-10-31.
- Refresh: ongoing.
- Use: site power, addresses, construction notes, and dates.
- Known issues: MW figures and dates are Epoch's estimates, not metered values. `gpu_clusters.csv`,
  named in the build plan, returns 404. Rows dated after the freeze are projections and are not used
  for power or dates. The list is incomplete. `Current power (MW)` matches IT power, so the analysis
  uses `Power (MW)` from the timelines.

## Census geocoder

- URL: `https://geocoding.geo.census.gov/geocoder/locations/onelineaddress`
- License: public domain (US government).
- Use: first choice for site coordinates.
- Known issues: it matched only 35 of 77 US site addresses, because many sites are new. See Amendment
  1 in [analysis_plan.md](analysis_plan.md).

## Census Gazetteer and Population Estimates

- URLs: `https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/` and
  `https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/co-est2025-alldata.csv`
- License: public domain (US government).
- Use: ZIP centroids as a location fallback, and county centroids and populations for weather weights.
- Known issues: the population file is Latin-1, and a ZIP centroid is only an approximate site
  location.

## Census state boundaries

- URL: `https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_20m.zip`
- License: public domain (US government).
- Use: the base map in Figure 1 only.

## Balancing authority polygons

- URL: Esri's `Balancing_Authorities_Summary` feature layer, built on EIA data.
- License: Esri Master License Agreement. This is not an open license, which is a known tension with
  the project's free-data goal.
- Use: point lookups only. Only the resulting BA codes are stored. The polygons are not stored or
  redistributed.
- Known issues: polygons overlap. 10 of the 60 powered sites fall inside more than one, and those sites
  cannot satisfy the go test. HIFLD, named in the build plan, did not return usable data. The layer
  sometimes answers a query with HTTP 200 and an error body, which the ingest retries. Anyone
  reproducing this work depends on Esri keeping the layer available.

## Open-Meteo Historical Weather

- URL: `https://archive-api.open-meteo.com/v1/archive`
- License: CC BY 4.0.
- Attribution: Weather data by [Open-Meteo.com](https://open-meteo.com/).
- Use: hourly temperature and relative humidity for 121 counties, 2019-01-01 to the freeze.
- Known issues: this is reanalysis weather at a county centroid, not a station reading.

## Hand-entered rows

Every hand-entered row has a citation in its own file.

| File | Rows | Purpose |
|---|---|---|
| [site_locations.csv](../dbt/seeds/site_locations.csv) | 5 | ZIP for sites no automatic method could locate |
| [site_flags.csv](../dbt/seeds/site_flags.csv) | 1 | On-site power flag for Colossus 1, which Epoch's text does not mention |
| [sub_ba_sites.csv](../dbt/seeds/sub_ba_sites.csv) | 6 | Sites assigned to the AEP zone. Three are marked `estimated` |
