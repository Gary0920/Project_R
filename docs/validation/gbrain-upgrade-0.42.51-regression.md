# GBrain 0.42.51 Regression Record

Date: 2026-06-18

Updated: 2026-06-20

## Regression Targets

| Area | Evidence | Result |
|---|---|---|
| `0001` Ollama embedding limits | `patches/gbrain/0.42.51/0001-ollama-local-embedding-limits.patch`; `bun run typecheck` | Passed typecheck. |
| `0002` recursive chunk cap | `patches/gbrain/0.42.51/0002-recursive-chunker-local-ollama-cap.patch`; `bun run typecheck` | Passed typecheck. |
| `0003` think source scope | `test/takes-engine.test.ts`; `test/think-pipeline.serial.test.ts` | Scalar `sourceId` and federated `sourceIds/allowedSources` tests passed. |
| `0004` agent-bound OAuth client registration | `test/auth-register-client-args.test.ts`; `test/oauth.test.ts` | Bound tool/source/slug/budget parsing and persistence tests passed. |
| `0005` subagent tool source scope | `test/brain-allowlist.serial.test.ts` | `buildBrainTools` scopes tools to submitted source id. |
| `0006` AI SDK v6 gateway loop | `test/ai/gateway-tool-loop.test.ts` | 7 gateway loop tests passed. Patch remains absorbed by upstream. |
| `0007` CJK title-like gather variants | `test/think-pipeline.serial.test.ts` | `gatherQuestionVariants('书面化原则是什么')` includes `书面化原则`. |
| `0008` doctor resolver health on Windows | `test/check-resolvable.test.ts`; `test/check-resolvable-cli.test.ts`; `test/doctor-behavioral.test.ts` | CRLF skill frontmatter parsing and Windows path separator assertions passed. |
| `0009` Windows/source-run migration subprocesses | `test/fix-wave-structural.test.ts`; temporary PGLite CLI migration chain | `apply-migrations` v0.11-v0.13 no longer requires a globally installed `gbrain` command when running from `bun run src/cli.ts`. |

Selected upstream command:

```powershell
bun test test/auth-register-client-args.test.ts test/oauth.test.ts test/brain-allowlist.serial.test.ts test/takes-engine.test.ts test/think-pipeline.serial.test.ts test/ai/gateway-tool-loop.test.ts
```

Observed result after `0009`: 305 pass, 0 fail, 1183 assertions across the selected patch/regression suite.

Additional resolver/doctor command:

```powershell
bun test test/check-resolvable.test.ts test/check-resolvable-cli.test.ts test/doctor-behavioral.test.ts test/brain-score-breakdown.test.ts
```

Observed result: 79 pass, 0 fail.

Additional Windows source-run migration validation:

```powershell
bun run .\src\cli.ts init --migrate-only
bun run .\src\cli.ts apply-migrations --yes --non-interactive --no-autopilot-install
bun run .\src\cli.ts apply-migrations --yes --non-interactive --no-autopilot-install
bun run .\src\cli.ts apply-migrations --list
```

Observed result on a temporary PGLite `GBRAIN_HOME`: `TEMP_MIGRATION_CHAIN_OK`; all orchestrator migrations through `0.32.2` applied, re-run was idempotent, and `--list` exited 0.

## Project_R Link Regression

Project_R remains a GBrain adapter/client, not a GBrain replacement.

Validated behavior:

- Project_R `/query` response can include normalized GBrain think citations as a visible `引用来源` section.
- Project_R `/query` response can include gaps, conflicts, and warnings as a visible `GBrain 诊断` section.
- Source scope rules remain unchanged:
  - personal workspace queries only `company-wiki`
  - project workspace queries `company-wiki + current project source`
  - customer workspace queries customer intelligence only

Backend command:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

Observed result:

- 44 passed, 13 warnings.
- `tests/conftest.py` now disposes the SQLAlchemy engine before unlinking the temporary SQLite database, fixing the Windows teardown lock without skipping tests.

Full backend command:

```powershell
.\venv\Scripts\python.exe -m pytest
```

Observed result:

- 613 passed, 1 skipped, 13 warnings.
- The skipped case is the real-project quality fixture source-file validation when Gary's local source sample files are not present in the checkout.

## Runtime Regression

Temporary runtime validation was constrained to `backend/workspace_data/_gbrain_upgrade_test/stage4_6_current`.

| Command family | Result |
|---|---|
| `init --pglite --no-embedding --skip-embed-check --json --force` | Exit 0, initialized empty PGLite runtime and schema. |
| `doctor --fast --json` | After `0008`, warnings-only: `health_score=90`, `brain_checks_score=100`, `resolver_health=ok`. |
| `apply-migrations --yes` | Exit 0, post-upgrade migration flow completed with non-blocking upstream warnings. |

`gbrain upgrade` was not run because it is a self-update path that can mutate global install state.

## Remaining Risks

| Risk | Classification | Next decision |
|---|---|---|
| `retrieval_reflex_health` remains warning | Host policy/integration skill not installed | Non-blocking for current Project_R runtime; track separately if retrieval-reflex is adopted. |
| `0003` and `0007` overlap in `src/core/think/gather.ts` | Patch maintenance risk | Prefer keeping the rebase branch or converting to sequential commits before future upgrades. |
| `0008` is Windows-sensitive | Patch maintenance risk | Keep CRLF parser regression tests when rebasing again. |
| `0009` depends on CLI invocation shape | Patch maintenance risk | Keep source-run Windows migration validation when rebasing again. |

## Go / No-Go

Stage 7-8 is no longer blocked by patch compilation, selected regression tests, or `doctor` resolver health.

Formal switch was completed on 2026-06-20; see `docs/validation/gbrain-upgrade-0.42.51-cutover.md`.
