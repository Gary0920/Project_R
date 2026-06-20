# GBrain 0.42.51 Switch Decision

Date: 2026-06-18

Updated: 2026-06-20

## Decision

Stage 7 decision: choose **方案 C：Project_R fork / pinned branch** as the target maintenance strategy for GBrain 0.42.51.

Stage 8 status: **completed on 2026-06-20**.

`reference/gbrain-master` has been replaced with the validated `0.42.51.0` candidate. The cutover record is `docs/validation/gbrain-upgrade-0.42.51-cutover.md`.

## Evidence Read

| Evidence | Relevant result |
|---|---|
| `docs/validation/gbrain-upgrade-0.42.51-rebase.md` | Required patch artifacts exist; typecheck, selected tests, build, temporary init, and `apply-migrations --yes` passed. |
| `docs/validation/gbrain-upgrade-0.42.51-regression.md` | 305 upstream selected tests passed after `0009`; Project_R GBrain-related tests passed after fixing Windows temp SQLite cleanup. |
| `docs/validation/gbrain-upgrade-0.42.51-cutover.md` | Runtime health returns `version=0.42.51.0`; real PGLite brain migrated schema `107` to `119`; post-cutover doctor is warnings-only. |
| `patches/gbrain/0.42.51/README.md` | `0001`-`0005` are rebased; `0006` is absorbed; `0007` is rebased with logical overlap against `0003`; `0008` fixes Windows doctor resolver hygiene; `0009` fixes Windows/source-run migration subprocesses. |
| `docs/adr/0008-gbrain-upstream-maintenance-policy.md` | If the patch set grows beyond a small number of files, Project_R should switch from patch files to fork/submodule strategy. |
| `docs/milestones/Project_R 开发流程V2.3_Gbrain升级.md` | If key patches remain, prefer fork; if most patches are absorbed, prefer submodule; short-term replacement is only a transition option. |

## First Action Result

Current Stage 7 entry is valid:

- `reference/gbrain-upstream-0.42.51` is on `project-r-0.42.51-rebased`.
- `VERSION` is `0.42.51.0`.
- `HEAD` is `9bf96db807c2f050449142f2f0b05726f58e5054`.
- Protected path check is empty for:
  - `reference/gbrain-master`
  - `backend/app.db`
  - `backend/workspace_data/_gbrain`
  - `backend/workspace_data/user`
  - `backend/workspace_data/project`
  - `backend/workspace_data/customer`

2026-06-20 Stage 8 cutover result:

- `doctor --fast --json` no longer reports `unhealthy`.
- `resolver_health` is `ok`: 52 skills, all reachable.
- Live service health is `status=ok`, `version=0.42.51.0`, `engine=pglite`.
- Old source and runtime data backups were created before replacement.

## Options

| Option | Decision | Reason |
|---|---|---|
| 方案 A：replace `reference/gbrain-master` | Executed as the local cutover mechanism | Used after resolver health was fixed and backups/runbook were complete. |
| 方案 B：Git submodule | Not selected now | Useful only when Project_R no longer carries key long-lived patches. `0003`/`0004`/`0005` remain critical. |
| 方案 C：Project_R fork / pinned branch | Selected | Best fit while Project_R still needs source-scope, agent-bound OAuth, subagent source-scope, and CJK title-query behavior that is not fully upstreamed. |

## Cutover Rationale

The technical rebase is healthy enough for continued preparation:

- GBrain typecheck passed.
- Selected patch tests passed: 201 pass, 0 fail.
- Build passed.
- Temporary runtime init passed.
- Temporary `apply-migrations --yes` passed.

2026-06-18 Stage 7 pre-cutover recheck:

- `bun run typecheck`: exit 0.
- `bun test test/auth-register-client-args.test.ts test/oauth.test.ts test/brain-allowlist.serial.test.ts test/takes-engine.test.ts test/think-pipeline.serial.test.ts test/ai/gateway-tool-loop.test.ts`: exit 0, 201 pass, 0 fail, 673 assertions.
- `bun run build`: exit 0.
- `.\venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py`: 44 items reached 100% pass progress, then pytest exited 1 during Windows temporary SQLite unlink in `tests/conftest.py`.

The original Stage 8 block was removed before replacement:

- `patches/gbrain/0.42.51/0008-doctor-resolver-health-windows-crlf.patch` fixed the Windows CRLF frontmatter parser issue, missing `skill-optimizer` resolver row, and Windows path separator test assumptions.
- `patches/gbrain/0.42.51/0009-windows-source-run-apply-migrations.patch` fixed source-run `apply-migrations` on Windows when no global `gbrain` executable is installed.
- `doctor --fast --json` changed from `status=unhealthy`, `health_score=65`, `resolver_health=fail` to `status=warnings`, `health_score=90`, `resolver_health=ok`.
- Remaining warning is `retrieval_reflex_health`; Project_R does not rely on that host policy integration for the current runtime path.

## Backup And Rollback

Rollback artifacts:

- Previous source tree: `reference/gbrain-master.pre-0.42.51-20260620-124345`
- Previous runtime data: `backend/workspace_data/_gbrain_backup_pre_0.42.51_20260620-124345`

See `docs/validation/gbrain-upgrade-0.42.51-cutover.md` for rollback steps.

## Go / No-Go

| Target | Status |
|---|---|
| Continue Stage 7 documentation and strategy preparation | Go |
| Prepare fork/pinned branch strategy | Go |
| Replace `reference/gbrain-master` | Completed |
| Run post-cutover production validation | Completed |
