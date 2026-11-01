# AI Power Atlas

Is AI data center growth already visible in US grid demand, and where?

There is no finding yet. Milestone M1, the feasibility spike, ended in a narrow
[go](docs/adr/0002-m1-go-or-pivot.md): [two small-BA sites](docs/m1_detectability.md) are large enough
to detect, and no eligible campus in PJM, ERCOT, or SOCO is large enough at BA level. No effect has
been measured. See [docs/PLAN.md](docs/PLAN.md) for the plan,
[docs/analysis_plan.md](docs/analysis_plan.md) for the method fixed before any results,
[docs/source_status.md](docs/source_status.md) for what each data source returned on the last check,
and [docs/log.md](docs/log.md) for what has been learned so far.

## Quickstart

Needs git, make, uv, and Docker with Compose v2. With Colima, run `colima start` after a reboot.

```bash
make setup
make up
make ci
make sources-check
```

`make setup` creates `.env`. Before running `make sources-check`, add a free
[EIA API key](https://www.eia.gov/opendata/register.php), a free
[Census API key](https://api.census.gov/data/key_signup.html), and a contact address for SEC EDGAR.

`make sources-check` rewrites `docs/source_status.md` and exits 1 if any source returned neither
records nor a page. LBNL and FCC block scripted requests, so expect that exit until those two rows
change. [docs/log.md](docs/log.md) has the details.
