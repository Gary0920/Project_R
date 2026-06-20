# GBrain 0.42.51 Rebase Validation

Date: 2026-06-18

## Baseline

| Item | Result |
|---|---|
| Upstream candidate | `reference/gbrain-upstream-0.42.51` |
| Branch | `project-r-0.42.51-rebased` |
| `VERSION` | `0.42.51.0` |
| `HEAD` | `9bf96db807c2f050449142f2f0b05726f58e5054` |
| Protected Project_R paths | clean |

Protected path command:

```powershell
git status --short -- reference/gbrain-master backend/app.db backend/workspace_data/_gbrain backend/workspace_data/user backend/workspace_data/project backend/workspace_data/customer
```

Observed result: empty output.

## Patch Set

Versioned artifacts were generated under `patches/gbrain/0.42.51/`.

| Patch | Status | Artifact |
|---|---|---|
| `0001` | `rebased` | `patches/gbrain/0.42.51/0001-ollama-local-embedding-limits.patch` |
| `0002` | `rebased` | `patches/gbrain/0.42.51/0002-recursive-chunker-local-ollama-cap.patch` |
| `0003` | `rebased` | `patches/gbrain/0.42.51/0003-think-source-scope-gather-and-takes.patch` |
| `0004` | `rebased` | `patches/gbrain/0.42.51/0004-agent-bound-oauth-client-registration.patch` |
| `0005` | `rebased` | `patches/gbrain/0.42.51/0005-subagent-tool-source-scope.patch` |
| `0006` | `absorbed_by_upstream` | no artifact |
| `0007` | `rebased_logical_overlap` | `patches/gbrain/0.42.51/0007-think-gather-title-query-variants.logical.patch` |

`0003` and `0007` both touch `src/core/think/gather.ts`. The concrete branch diff folds the title-query variant hunk into the same gather stream as source-scope forwarding. The versioned patch README documents that dependency.

## Project_R Adapter Optimization

`backend/app/features/knowledge/sources.py` now appends a user-visible summary when normalized GBrain think sources include:

- `gbrain_think_citation`
- `gbrain_think_gap`
- `gbrain_think_conflict`
- `gbrain_think_warning`

This keeps Project_R at the adapter boundary: Project_R displays GBrain output clearly but does not copy GBrain query, graph, citation-fixer, enrichment, or schema internals.

## Install And Build Validation

Run from `reference/gbrain-upstream-0.42.51`.

| Command | Exit | Result |
|---|---:|---|
| `bun install --frozen-lockfile` | 1 | Failed on Windows postinstall shell redirection. No dependency changes. |
| `bun install --frozen-lockfile --ignore-scripts` | 0 | Checked 285 installs across 277 packages, no changes. |
| `bun run typecheck` | 0 | `tsc --noEmit` passed. |
| `bun test test/auth-register-client-args.test.ts test/oauth.test.ts test/brain-allowlist.serial.test.ts test/takes-engine.test.ts test/think-pipeline.serial.test.ts test/ai/gateway-tool-loop.test.ts` | 0 | 201 pass, 0 fail, 673 assertions. |
| `bun run build` | 0 | Bundled 1702 modules and compiled `bin/gbrain.exe`. |

`test/think-pipeline.serial.test.ts` now includes direct regression coverage for conservative CJK title-like query variants.

## Embedded Runtime Validation

Runtime validation used only `backend/workspace_data/_gbrain_upgrade_test/stage4_6_current`.

Environment policy:

- Temporary `GBRAIN_HOME`, `HOME`, `USERPROFILE`, `XDG_CONFIG_HOME`, and `XDG_DATA_HOME` pointed inside the temp folder.
- `apply-migrations` used a temporary `gbrain.cmd` shim under the temp folder because upstream shells out to bare `gbrain`.
- No formal `backend/workspace_data/_gbrain`, user, project, customer, or app DB path was used.

| Command | Exit | Result |
|---|---:|---|
| `bun run <upstream>/src/cli.ts init --pglite --no-embedding --skip-embed-check --json --force` | 0 | PGLite init succeeded, pages 0, embedding check skipped intentionally. Schema migrations reached 119. |
| `bun run <upstream>/src/cli.ts doctor --fast --json` | 1 | `status=unhealthy`, `brain_checks_score=100`, `health_score=65`. Failure category is skill/resolver hygiene, not a patch regression. |
| `bun run <upstream>/src/cli.ts apply-migrations --yes` | 0 | Applied post-upgrade migration flow successfully. Output ended with upstream warnings: no repo path, missing `auto_link` config, and Windows path message. |

## Why `gbrain upgrade` Was Skipped

Source inspection shows `gbrain upgrade` is a self-update command, not an embedded Project_R dependency migration:

- `src/commands/upgrade.ts` usage says it self-updates the CLI and detects install method.
- It can run linked-repo update instructions such as `git pull && bun install`.
- It can run package update flows such as `bun update gbrain`.
- It can replace binaries.
- It can run `clawhub update gbrain`.
- It can call `gbrain post-upgrade`.

This exceeds the isolated runtime validation boundary, so this stage uses `init`, `doctor`, and `apply-migrations` only.

## Project_R Backend Validation

Run from `backend`:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

Observed result:

- 44 items collected.
- `tests/test_gbrain_config.py`: passed.
- `tests/test_gbrain_project_sources.py`: passed.
- `tests/test_knowledge_browser.py`: passed.
- Pytest process exited 1 during `pytest_sessionfinish` because Windows held the temporary SQLite DB file open in `tests/conftest.py`.

Classification: test assertions passed; final exit is a Windows teardown/environment risk already called out in the goal. Tests were not edited to hide it.

## Stage 7-8 Recommendation

Recommendation: conditional go for continuing technical preparation, no-go for formal replacement of `reference/gbrain-master` until Gary accepts or resolves the upstream `doctor` resolver/skill hygiene failure.

Reasons:

- Required Project_R patches have rebased artifacts.
- Typecheck, selected patch tests, and build passed.
- Temporary runtime init and migrations succeeded without touching formal data.
- `doctor` still returns `unhealthy` due upstream skill resolver issues, even though brain checks score 100.
