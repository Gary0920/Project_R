# ADR 0014: GBrain Maintenance Worker Strategy

Date: 2026-06-02

## Status

Accepted, amended by [ADR 0019: GBrain-Ready Preprocessing Source Repos](0019-gbrain-ready-preprocessing-source-repos.md)

## Context

Project_R runs GBrain as an external knowledge-base kernel with a local PGLite brain. GBrain provides native Postgres worker capabilities but the current Project_R installation uses PGLite, not a persistent Postgres instance.

Project_R already has a gbrain_maintenance_worker.py daemon thread that periodically:

- Ticks Dream Cycle (submit scheduled maintenance jobs against company-wiki source)
- Polls tracked Dream Cycle jobs for terminal status transitions
- Polls tracked citation-fixer jobs and reconciles GBrain sidecars back to the current GBrain source repo. In the MVP this is `derived/`; after ADR 0019 migration it should be the relevant `gbrain-ready/` repo.
- Runs the contradiction probe CLI against company-wiki
- Writes audit records and notifies system admins on errors

The worker runs inside the Project_R backend process and does not depend on a GBrain Postgres worker process.

## Decision

### Primary strategy: Project_R daemon thread + PGLite inline

1. The gbrain_maintenance_worker.py daemon thread is the canonical long-running maintenance scheduler. It starts on backend init (gated by PR_GBRAIN_MAINTENANCE_WORKER_ENABLED, default on), runs at configurable intervals (default 300 s), and exposes status through GET /admin/knowledge/gbrain/maintenance and the admin frontend worker diagnostic card.

2. GBrain native Postgres worker is deferred. It remains documented as available in docs/gbrain-feature-inventory.md but is not on the current roadmap.

3. PGLite inline execution is accepted as the current path. GBrain jobs submit subagent runs inline within the PGLite process. The maintenance worker job tracking works correctly against PGLite jobs.

### What runs automatically (no admin confirmation)

| Task | Auto | Rationale |
|---|---|---|
| Dream Cycle tick (submit autopilot-cycle) | Yes | Read-only maintenance check; GBrain autopilot-cycle does not mutate pages |
| Dream Cycle poll (track KB jobs to terminal) | Yes | Read-only status checks; transitions trigger notifications |
| Citation-fixer poll (reconcile sidecar to source repo) | Yes | Only polls admin-submitted jobs; reconciliation preserves source-repo audit. MVP writes back to `derived/`; ADR 0019 moves target audit to `gbrain-ready/`. |
| Contradiction probe tick | Yes | Read-only discovery; produces flagged contradictions, never auto-fixes |
| Worker error notification | Yes | Critical errors always notify system admins via notification center |

### What requires admin confirmation

| Task | Admin-only |
|---|---|
| Citation-fixer submission (POST /admin/knowledge/gbrain/citation-fixer) | Yes |
| Dream Cycle config (interval, job names, target score) | Yes |
| Contradiction probe config (queries, judge model, budget) | Yes |
| Rollback of citation-fixer job | Yes |
| Forced Dream Cycle or contradiction probe run | Yes |

### Hard rule: No automatic unattributed rewrites of company knowledge

The worker must never automatically modify GBrain-ready Markdown files without a traceable admin action. The only path that writes back to the GBrain source repo is citation-fixer job reconciliation (triggered when a previously admin-submitted citation-fixer reaches terminal state) and explicit admin rollback. The contradiction probe is read-only discovery. The MVP writes back to `derived/` with local Git audit; after ADR 0019 migration, the same audit requirement applies to `gbrain-ready/` plus manifests and audit logs.

## Consequences

- Maintenance worker strategy is documented and unambiguous. Future agents must not upgrade to GBrain Postgres worker without updating this ADR.
- Admin frontend must continue to display the worker diagnostic card.
- The gbrain-maintenance-worker thread is daemon-mode; it does not survive backend restart without explicit start.
- GBrain native Postgres worker remains deferred; if enabled later this ADR must be superseded.
