# Build log

## M0 Foundation (2026-10-31)

Differences between the plan and what the sources do today:

- `gpu_clusters.csv` from Epoch returns 404. `data_center_timelines.csv` exists, with dated
  construction status and power per site. M1 needs those dates for energization.
- `data_centers.csv` has no date column, so the timelines file is the only source of timing.
  97 of its 575 rows are dated after 2026-10-31, running to 2030, and are Epoch's estimates. The
  event study must use past dates only and must not treat an estimate as an observed energization.
- The EIA public `DEMO_KEY` answered all seven routes once, then returned 429. It is enough to
  confirm the routes and too limited for a backfill, which needs a personal key.
- LBNL (Cloudflare) and FCC (Akamai) return 403 to scripted requests. The LBNL page loads in a
  browser and links `LBNL_Ix_Queue_Data_File_thru2025.xlsx`. The FCC page opened in a browser but
  returned no readable text, so its download is not confirmed. Neither block is being worked
  around. Files get downloaded by hand into `raw/files/`.
- HIFLD control-areas pages and services did not return usable data. Esri's
  `Balancing_Authorities_Summary` layer, built on EIA data, has 60 BA polygons with EIA codes and put
  New Carlisle in PJM, Memphis in TVA, and Abilene in ERCO. It is under the Esri Master License
  Agreement, so M1 queries it and stores only the BA codes.
- `api.census.gov` now redirects to a missing-key page, so ACS needs a key even though the plan
  lists the Census account as optional. The Population Estimates county file on www2.census.gov
  needs no key and covers the population weights for BA temperature, so M1 does not depend on ACS.
- The old MISO `getfuelmix` broker URL returns "no data". The probe uses
  `public-api.misoenergy.org` instead.
- Overpass returned 406 to the default httpx User-Agent and 502 when at capacity. One failed check
  does not mean the source is gone.

Differences between the plan and the stack:

- `minio/minio` no longer exists on Docker Hub and the upstream GitHub repo is archived. The stack
  uses the frozen `bitnamilegacy/minio` image, which is fine for a local lake but gets no updates.
- The Airflow webserver died 11 minutes after start on an 8 GB laptop when gunicorn missed its
  heartbeat. It now runs one worker and restarts on failure, and stayed healthy for over 3 hours.
- macOS AirPlay Receiver holds port 5000 and answers 403, so MLflow is published on 5001.

Plan tooling not set up yet: `sqlfluff` and `nbstripout` wait for the first SQL and notebooks.
`commitlint` and `release-please` wait for the GitHub repo.

Gate decision (Vijay, 2026-10-31): start M1 with these gaps open. LBNL and FCC stay blocked for
scripts and become manual downloads. eGRID, PJM, ERCOT, SPP, Aqueduct, and TIGER have only had their
pages checked. Agent skills are not installed.
