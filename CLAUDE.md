# Agent Rules — AI Power Atlas

## Authorship (non-negotiable)
- Vijay Shankar Chamakuri is the ONLY author. Never add `Co-Authored-By`, `Claude-Session`,
  "Generated with ...", or any AI attribution to commits, PRs, code comments, or docs.
- Do NOT run `git commit` or `git push` unless explicitly told to. Default: stage changes and
  propose a Conventional Commit message; Vijay commits.
- Never change git config (user.name / user.email).

## Workflow
- Local-first. Everything must run with `make up && make pipeline && make test` on a laptop
  before anything touches the cloud or GitHub.
- Plan → test → implement → verify. Write or extend tests before or with each change.
- Small, reviewable changes: one concern per change, < ~400 changed lines.
- Before saying a task is done, run `make ci` and paste the summary. No "should work".

## Code standards
- Python 3.12, managed with `uv`. Type hints everywhere; `ruff` + `mypy --strict` must pass.
- SQL lives in dbt only (no SQL strings scattered in Python, except the guarded LLM layer).
  `sqlfluff` must pass.
- No secrets in code. Read from env vars via `pydantic-settings`; keep `.env.example` updated.
- No notebooks in `src/`. Notebooks only in `notebooks/`, outputs stripped (`nbstripout`).
- Every data source gets: a raw schema contract, a freshness check, and a row-count test.
- Log with `structlog` (JSON). No `print`.
- Do not invent data, metrics, or results. If a number is not computed from the pipeline,
  it does not go in the README.

## Real data only (non-negotiable)
- NEVER generate synthetic, mock, simulated, or "example" datasets. Every row must come from a
  source listed in docs/PLAN.md §7 and carry `_source`, `_source_url`, `_ingested_at` columns.
- If a source is unreachable, STOP and report it. Do not fabricate a fallback.
- Test fixtures = small slices of REAL API responses recorded with `vcrpy`/`pytest-recording`,
  stored in tests/fixtures/ with the date pulled.
- The demo dataset = a real 30-day extract produced by `make sample-data`, not generated.
- Any hand-curated row (e.g. a data center seed) must have a public citation URL.

## Anti-slop rules
- No placeholder functions, TODO stubs, or fake data presented as real.
- No emojis in code, logs, or commit messages.
- Prefer deleting code to adding abstraction. No class unless it holds state.
- Docstrings say WHY, not WHAT.
- README claims must link to the notebook, test, or dashboard that proves them.

## Things that make a repo read as AI-generated (avoid all of them)
Code:
- Comments that narrate the next line ("# Loop through the rows"). Comment only non-obvious decisions.
- Over-defensive try/except around everything, or catching bare `Exception` and logging "An error occurred".
- Wrapper classes, factories, and "managers" with one caller. Generic names: `utils.py`, `helpers.py`,
  `process_data()`, `handle_request()`, `DataProcessor`.
- Identical boilerplate docstrings on every function; Args/Returns blocks that repeat the type hints.
- Unused dependencies or imports, dead config flags, functions never called.
- Print-banner logging ("==== Starting pipeline ====") and emoji in logs or CLI output.
- Magic numbers with no source. Every threshold (z-score cutoff, weights) lives in config with a
  one-line reason.

Docs and README:
- Words to avoid: leverage, seamless, robust, cutting-edge, comprehensive, powerful, delve,
  unlock, empower, revolutionize, state-of-the-art, game-changer, "in today's fast-paced world".
- No emoji section headers, no badge walls (max 5 badges), no rocket emojis.
- No "Features" list of 15 bullet points. Show 3 results with numbers and a GIF instead.
- No "Future work" list longer than the shipped work.
- Write like an engineer's notes: short sentences, specific nouns, real numbers, stated limitations.
- Every chart has a title that states the finding ("MISO evening peak rose [X]% after [event]"), not
  "Demand over time".

Git:
- No single giant "Initial commit" containing the whole project. Commit as you build, in small steps.
- Never backdate or fake commit timestamps. An honest timeline is fine.
- Commit messages describe the change specifically: `feat(ingest): paginate EIA fuel-type pulls by
  month`, not `Update files` or `Implement comprehensive data pipeline`.
- No committed `.DS_Store`, `__pycache__`, `.env`, notebook outputs, or huge data files
  (data stays in the lake; a real sample Parquet under 20 MB is the only exception).

Analysis:
- Report baselines, errors, and failures alongside wins. Overly clean results are a red flag.
- State limitations in the README in plain words (EIA revisions, incomplete data center list,
  BA≠county).
