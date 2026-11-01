# ADR-0003: Keep commit history instead of squash-merging

Status: accepted.

Date: 2026-11-01

## Context

The build plan asks for squash-merge pull requests. This project's main evidence of pre-registration is
commit order: the analysis plan and its amendments land before the model and the results. A squash would
collapse that order into one commit and destroy the proof.

## Decision

Pull requests merge by rebase or fast-forward, never by squash. Each commit stays small and must pass `make
ci` by itself. The M1 history reached `main` by fast-forward for this reason.

## Consequences

The history is longer than a squash workflow would leave. It stays honest and can be checked commit by
commit. This overrides the squash-merge line in section 9 of [docs/PLAN.md](../PLAN.md).
