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

## M1 Ingest (2026-10-31)

Freeze date 2026-10-31. Snapshots are stored once under `raw/files/` and never replaced:

| File | SHA-256 |
|---|---|
| `epoch/data_centers.csv` | `f43d33c8b7612da0a46f51ad207169ac487f54989df3acaafbb2e0453f54a5ce` |
| `epoch/data_center_timelines.csv` | `67c983eb002c7fb48a448cb181e4d0acc6c6dcca2f46800e6b58f0a8961ac1a3` |
| `census_zcta/zcta.zip` | `7b85c04a131672f58b38a950eb82855d5fd4054f0bd9bc3f69aa28897a714e3d` |
| `census_counties/counties.zip` | `3c337402b5c6e8d5aa26b4278ccf4edc8989f2683765b3ffbf22296cdb2df3a0` |
| `census_population/co-est2025-alldata.csv` | `4f5a499d851e2cb48fd7a5405e5a9235453a8a66933657aacd10df0e264f35d5` |

Site mapping for the 60 US sites with power by the freeze: 29 by Census geocoder, 19 by ZIP
centroid, 7 by Epoch's Google Earth links, 5 by hand-entered ZIP with a citation, 0 unlocated. The
geocoder and the Earth links agreed on the BA for the 4 sites that had both. 10 sites fall inside more
than one BA polygon and cannot satisfy the go criterion (Amendment 1).

`behind_meter_risk` list, fixed before any minimum detectable MW is computed: Colossus 2, OpenAI
Stargate Abilene, Meta Prometheus, Meta Bowling Green, Meta Hyperion, OpenAI Stargate New Mexico, from
Epoch's text, and Colossus 1, by hand. Epoch does not mention turbines at Colossus 1, but
[DCD reports](https://www.datacenterdynamics.com/en/news/campaigners-appeal-decision-to-permit-gas-turbines-at-xais-memphis-data-center/)
a permit for 15 gas turbines at xAI's Memphis site.

LightGBM's macOS wheel needs `libomp`, and this Mac has no Homebrew. `scripts/link_libomp.sh` points
LightGBM at the copy inside scikit-learn's wheel, changing only `.venv`.

EIA-930 region data: 2,861,089 rows of `D` and `DF` for 21 BAs, plus 68,354 sub-BA rows for PJM's AEP
zone, 2019-01 to the freeze. WACM has no rows after 2026-04-02 (Amendment 2). Hours with no value are
kept as nulls: SRP has the most, 243 of about 68,600.

Candidates from the 2% rule: WALC, SRP, AZPS, PGE, PNM, PACW, IPCO, TVA, BPAT, SWPP, PJM, SOCO, ERCO,
NEVP. WACM passes on share but its data ends before Meta Cheyenne starts. MISO misses at 1.76%. WALC's
31% share comes only from three Phoenix-area sites inside overlapping polygons, so it cannot produce a
go by itself.

Weather: 121 counties, 8,308,344 hourly rows from Open-Meteo, 2019-01-01 to the freeze, with no null
temperatures. AZPS, SRP, and PGE have fewer than 10 counties whose centroid falls inside their polygon
(6, 1, and 4), so they use what exists. SRP's one county is Maricopa. WACM's counties were pulled before
Amendment 2 dropped it and are unused.

Parquet snapshots hold too many files to list. Each hash below is the SHA-256 of the sorted lines
`<file sha256>  <key>` for every file under that prefix:

| Prefix | Files | SHA-256 |
|---|---|---|
| `raw/eia/region_data/` | 1,968 | `bd2356744ea5c9bb5c35b863e354e3455a90a7e1d4cfc1fb1341cb5ad28b89b8` |
| `raw/eia/region_sub_ba_data/` | 94 | `31453db35c06720bd89919eb0cab531aa9a2d02ddfc9d0ce77a2724734a2dd69` |
| `raw/weather/` | 121 | `0beab0215a9ca193b7b10f97efa6078abe26baa8deab374945f8f041b8ed6a9b` |

## M1 Detectability (2026-11-01)

Full results: [m1_detectability.md](m1_detectability.md). Rerunning gave identical MDEs for all 15
series.

Process note: a run began against uncommitted code when a commit failed on a pre-commit fix. It was
stopped in under a minute and its output was deleted unread, then the code was committed and run. Any
MLflow runs it left carry the tag of the older commit, `786bf0b`.

The first complete run, at `bda458a`, stored no `e(t)` values. `1d0bbdb` stored them without changing
the model or method. The sensitivity table came after that and is labeled as not pre-registered.

## Clean rebuild (2026-11-01)

`make setup && make pipeline` ran from a fresh clone at `4f5a92c` into an empty bucket, in 63 minutes.
Its `docs/m1_detectability.md` matched the frozen run on every line except the commit ID. The Epoch
files had the same hashes. The first attempt stopped when the Esri layer answered HTTP 200 with an
error body, which the ingest now retries. `make up` used the existing checkout, because the Compose
project name is fixed and a second copy would have replaced the running stack's bind mounts.

On Linux in Docker, ruff and the tests passed. `mypy` ran out of memory in the 4 GB Colima VM there, so
GitHub's first CI run is its first Linux check.

## Figures (2026-11-01)

`atlas analyze figures` draws the eight figures in the README from the frozen lake. They came after the
clean rebuild above, so that rebuild did not exercise them. They use no demand on or after a BA's first
listed site. The chance of detection at a site's full power, in Figures 6 and 7, is read off each BA's
existing `e(t)` values. It is descriptive and not part of the go test.

Design followed the [Nature figure guide](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications),
[Ten Simple Rules for Better Figures](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4161295/), the
[CDC on forest plots](https://www.cdc.gov/wcms/4.0/cdc-wp/data-presentation/forest-plot.html), and the
[ONS on small multiples](https://service-manual.ons.gov.uk/data-visualisation/chart-types/small-multiple-charts).

## GitHub Actions triggers (2026-11-01)

GitHub at first recorded pushes to this repo but created no workflow runs for pushes or a pull request, while
manual runs worked. An [unanswered GitHub report](https://github.com/orgs/community/discussions/205033) describes
the same symptom. Turning Actions off and on, disabling and enabling both workflows, and listing push branches
explicitly cleared it. Those changes went in together, so the exact cause is unknown. Pushes and pull requests
have started runs since.

Working triggers then showed that the authorship check failed on pull requests, because GitHub writes the
temporary merge commit. The check now skips merge commits. Branch protection needs GitHub Pro on a private repo,
so nothing blocks a direct push to `main`.

## Rebuild with figures (2026-11-01)

A third full `make pipeline` run, at `05483d0`, stopped in the weather pull after 13 counties. Open-Meteo answered
"Daily API request limit exceeded", because each 8-year county pull counts as many requests and two earlier pulls
had used the day's quota. The ingest had given up rather than saying so. It now waits out minute and hour limits,
stops with a plain message on the daily limit, and keeps finished counties so a rerun resumes.

That run also showed that Epoch updated its files after the freeze, so the snapshot hashes differ. No site's power,
first date, or flag changed under the M1 rules. A fresh pull can therefore differ from the frozen inputs, and only
the backup reproduces them exactly.

To test what the failed run did not reach, a fresh clone of `main` at `ed14897` downloaded the data release, restored
it into an empty bucket, and ran `make setup`, `make lake-restore`, and `make analysis`. All 8 figures matched byte for
byte, and the results file matched except for the commit ID. So a full fresh pull with figures has not finished in one
run: the earlier fresh pull at `4f5a92c` predates the figures, and the figures have been tested on restored data.

## M2 commands (2026-11-01)

`atlas ingest m2` and `atlas analyze event-study` now exist and refuse to run before the freeze. Weather for the
control grids can take several days, because Open-Meteo limits daily use and the pull resumes. Tried on real data
before any listed site, the new path reproduced IPCO's stored estimate of -21.5275 MW. A dry run at a made-up start
date of 2023-01-01 labeled both grids `null`, and that output was discarded. Fixed in Amendment 4, the real run
happens once.
