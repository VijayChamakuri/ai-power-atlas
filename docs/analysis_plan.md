# Analysis plan

Written 2026-10-31, before any demand model was fit and before any demand residual was computed.
Changes after the first commit of this file go in the Amendments section, with a date and a reason.
A null result is published as a null result.

## What had been seen when this was written

- Epoch AI's site list and timelines, including site power and first dates.
- EIA row counts, latest dates, and the list of BA and sub-BA codes.
- No EIA demand values. The MISO probe in `atlas sources check` fetches real-time load but reads only
  its timestamp.
- The `behind_meter_risk` terms below were chosen after reading Epoch's timeline text, with no demand
  data in view.

## Question for this milestone (M1, v0)

Can the load of a large campus be detected in hourly balancing authority (BA) demand at all? M1
measures only the smallest step each method could detect. It does not estimate any campus's effect,
and it must not compute residuals on or after a real energization date.

## Data

Snapshots are frozen at the first ingest. The freeze date and SHA-256 of each file go in `docs/log.md`.

| Input | Source | Use |
|---|---|---|
| Demand (`D`), day-ahead forecast (`DF`) | EIA-930 `rto/region-data`, 2019-01-01 to freeze | Model target and benchmark |
| Site power and dates | Epoch `data_centers.csv`, `data_center_timelines.csv` | Candidate selection and treatment dates |
| Site coordinates | Census geocoder on Epoch addresses | Site to BA mapping |
| BA polygons | Esri `Balancing_Authorities_Summary` layer, built on EIA data | Point-in-polygon lookup only |
| County population, centroids | Census Population Estimates, Census Gazetteer | Weather weights |
| Temperature, humidity | Open-Meteo archive | Weather features |

The polygon layer is under the Esri Master License Agreement, not an open license. It is queried for
lookups, and only the resulting BA codes are stored. The polygons are not redistributed.

## Candidate selection

Only sites with `Country = United States` count. A site's power is `Power (MW)` on its latest timeline
row dated on or before the freeze. `Current power (MW)` in `data_centers.csv` is not used: it equals
the timeline's `IT power (MW)` for all 77 US sites, so it leaves out cooling and other overhead.

For each BA: `share = sum(site power at freeze, all US sites) / peak hourly demand over the last 12
months`. A BA is a candidate if `share >= 2%`, the starting threshold in the build plan. Epoch's rows
dated after the freeze are projections, and their dates and MW figures are never used.

A site's first date is its first timeline row with `Power (MW) > 0` on or before the freeze. A BA's
first site date is the earliest of these among its sites. These dates and MW figures are Epoch's
estimates from satellite imagery and permits, so they are labeled `estimated`, not `reported`. A site
with no usable address gets a hand-entered location with a public citation, or is excluded and listed.

A site is flagged `behind_meter_risk` if any of its timeline rows, including projected rows, contains
one of these terms, ignoring case: `turbine`, `behind-the-meter`, `behind the meter`, `on-site power`,
`on-site generation`, `power plant`, `power generation`, `fuel cell`, `microgrid`. On-site power may
never appear in BA demand, so a flagged site cannot satisfy the go criterion below. `generator` is not
a term because nearly every site lists backup diesel generators.

Text search only finds what Epoch wrote. The flag list goes in `docs/log.md` at the freeze, before any
minimum detectable MW is computed. Until then a site can be added by hand with a public citation. A
flag is never removed.

## Baseline model

Trees cannot extrapolate a trend, and an unextrapolated trend would look like new load. So the target
is demand minus a linear trend fit on the training window. LightGBM predicts that detrended target,
and the trend is added back.

Features: hour, day of week, month, US federal holiday, population-weighted temperature and humidity
(top 10 counties by population inside the BA), cooling and heating degree hours (base 65 F, the
convention used in US degree-day reporting). No lagged demand, because lags would absorb a step
change and hide the signal being measured.

Hours with demand at or below zero, or above three times the BA's median, are dropped from fitting
and counted in the results. Raw values are kept. The cutoff is a judgment call meant to catch reporting
errors, and the count shows whether it removed more than a few hours.

Reported per BA, out of sample: MAPE, RMSE, and peak-hour error, against seasonal naive (same hour
last week) and EIA's day-ahead forecast. No lags means this model should lose to both at short
horizons. Its job is weather normalization, not forecasting.

## Detectability

Pseudo-dates run every 30 days. For each pseudo-date `t`:

1. Train on all data up to `t - 365 days`, with at least 730 days of history so that the trend is not
   fit on a single season.
2. Predict the following 545 days, so every residual is out of sample.
3. Step estimate `e(t)` = mean daily residual in the 180 days after `t`, minus the mean over the 365
   days before `t`. Those windows include a full year before and half a year after.

The last 180-day window must end before the BA's first site date. This keeps the real effect out.

With no injected load, the `e(t)` values form the null distribution. A step is declared detected when
`e(t)` exceeds the null's 95th percentile (one-sided, 5% false positive rate). Adding `S` MW to demand
after `t` adds exactly `S` to `e(t)`, and the model is unchanged because `t` is after training. So:

`minimum detectable MW = q95(e) - q20(e)`, the smallest step detected in 80% of windows.

A test injects known steps into real series and confirms that this formula matches the detection rate.

BAs with fewer than 12 usable pseudo-dates, about one year of starting points, are reported as
`insufficient_history`, with no number. With data from 2019-01-01, that applies to any BA whose first
site date is before about June 2023. Epoch lists three US sites that early, so their BAs may get no
number.

Also reported per BA: MDE as a percent of peak, and for each site, `implied utilization = MDE / site
MW`. Epoch's figure is facility power, and a campus may draw well below it. Implied utilization shows
how hard the site would have to run to be seen, without assuming a load factor.

Secondary analysis: the same method on EIA sub-BA demand for candidate regions that report it, with
PJM's AEP zone included regardless of share because of the New Carlisle, Indiana site. Sub-BA mapping
is a hand seed with a citation per row. It reports alongside the BA results and cannot alone turn a
no-go into a go.

## Go or pivot

Go if at least one site without `behind_meter_risk`, in a candidate BA that has a minimum detectable
MW, has power at or above that number.

Otherwise pivot, using one of the options in the build plan: (a) restrict to small BAs, (b) aggregate
many campuses per ISO, or (c) lead with carbon (v2). Vijay makes this decision. ADR-0002 records it.

The go criterion accepts Epoch's power figure as stated. If it passes only for sites with implied
utilization above 80%, the ADR must say the evidence is weak. The 80% is a judgment call with no
published source, fixed here before any result exists.

## Known limitations

- Pseudo-dates 30 days apart share most of their windows, so the null has far fewer independent
  samples than dates. Percentile estimates are rough, and each MDE is reported with its sample count.
- Some BAs already held large data centers before their first Epoch date, and other load is growing
  too. Both widen the null, which makes MDE conservative but does not bias it toward a go.
- A site's first row with power can lag its real start. Epoch's Google Storey County notes say Building
  1 was first operational in 2021, but the first row with power is 2023-08-30. If that lag puts real
  load inside the null windows, the same widening applies.
- MDE measures a sharp step. Real campuses ramp over months, which is harder to detect.
- Detection says load appeared. It cannot alone attribute that load to a data center. M2 needs
  placebo dates and placebo BAs for that.
- BA polygons overlap and do not match county lines. Weather weighting is an approximation.
- The Epoch list is incomplete, so untreated BAs and pre-periods may contain unlisted campuses.
- EIA-930 revises recent hours and has known gaps.

## Outline for M2 (v1)

Before any residual is computed at a real energization date, an amendment here must fix the details
of: the event study with placebo dates and placebo BAs, synthetic control, 90% intervals, and the
sensitivity test shifting energization dates by 3 months. M2 does not start until that amendment is
committed.

## Amendments

### Amendment 1 (2026-10-31): locating sites and overlapping polygons

Reason: the Census geocoder found only 35 of 77 US site addresses, including none for Abilene or
Colossus 1, and some sites fall inside more than one BA polygon. Written before any demand value was
pulled.

Location order for each site with power by the freeze: (1) Census geocoder on Epoch's address, (2)
median coordinates of the Google Earth links in Epoch's own notes, (3) Census Gazetteer centroid of
the ZIP in Epoch's address, (4) a hand-entered ZIP in `dbt/seeds/site_locations.csv` with a citation.
Each site's method is stored and reported. A site still unlocated is excluded and listed. Sites with
no power by the freeze are not located, because they cannot change a share, a first date, or the go
test.

A site inside more than one BA polygon counts toward the share and first date of each of those BAs,
and cannot satisfy the go criterion. Polygons do not say which BA serves it, and this rule avoids
choosing one after results exist. If this rule alone decides go or pivot, the ADR must say so.

### Amendment 2 (2026-11-01): a BA whose data stops before the freeze

Reason: WACM's EIA-930 demand ends on 2026-04-02, around
[SPP's expansion into the Western Interconnection](https://www.powermag.com/spp-set-to-become-first-rto-straddling-eastern-and-western-interconnections/).
Written after seeing each BA's 12-month peak and site share, with no model fit and no residual
computed.

A BA's 12-month peak window ends at its last hour with data, not at the freeze, so a partial year
cannot leave out a summer peak. A BA whose data ends before its first site date is not a candidate,
because the site's load can never appear in that series. Peaks use the same cleaned hours as the
model. Raw peaks and dropped hours are stored next to them.
