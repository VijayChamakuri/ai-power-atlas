#!/usr/bin/env bash
# GitHub creates no workflow runs for pushes or pull requests in this repo, though it runs them when
# started by hand. See docs/log.md. This pushes, starts both checks, and fails if either fails.
set -euo pipefail
branch=$(git branch --show-current)
commit=$(git rev-parse HEAD)
git push origin "$branch"
gh workflow run ci.yml --ref "$branch"
gh workflow run authorship.yml --ref "$branch"
for workflow in ci.yml authorship.yml; do
  run_id=""
  for _ in $(seq 1 30); do
    run_id=$(gh run list --workflow "$workflow" --commit "$commit" --limit 1 --json databaseId \
      --jq '.[0].databaseId // empty')
    [ -n "$run_id" ] && break
    sleep 5
  done
  [ -n "$run_id" ] || { echo "No run appeared for $workflow" >&2; exit 1; }
  gh run watch "$run_id" --exit-status
done
