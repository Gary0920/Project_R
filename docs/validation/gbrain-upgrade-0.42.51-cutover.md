# GBrain 0.42.51 Cutover Record

Date: 2026-06-20

## Decision

Stage 8 formal cutover completed.

`reference/gbrain-master` now points to the validated `0.42.51.0` candidate from `reference/gbrain-upstream-0.42.51`.

## Backups

| Item | Backup path |
|---|---|
| Previous source tree | `reference/gbrain-master.pre-0.42.51-20260620-124345` |
| Previous runtime data | `backend/workspace_data/_gbrain_backup_pre_0.42.51_20260620-124345` |

The source tree and runtime data backups are intentionally local rollback artifacts and are not tracked by Git.

## Cutover Steps

1. Confirmed protected path check was empty before replacement:
   - `reference/gbrain-master`
   - `backend/app.db`
   - `backend/workspace_data/_gbrain`
   - `backend/workspace_data/user`
   - `backend/workspace_data/project`
   - `backend/workspace_data/customer`
2. Stopped any matching `bun.exe src/cli.ts serve --port 3131` process.
3. Copied `backend/workspace_data/_gbrain` to the backup path above.
4. Renamed the previous `reference/gbrain-master` to the source backup path above.
5. Copied `reference/gbrain-upstream-0.42.51` to `reference/gbrain-master`.
6. Restarted GBrain with `.\scripts\start-gbrain.ps1 -Restart`.

## Runtime Result

Health endpoint:

```json
{
  "status": "ok",
  "version": "0.42.51.0",
  "engine": "pglite"
}
```

Service log showed the live PGLite brain migrated from schema `107` to `119`; 12 migrations were applied.

## Doctor Result

Command family:

```powershell
bun run .\src\cli.ts doctor --fast --json
```

Run from `reference/gbrain-master` with `GBRAIN_HOME=backend/workspace_data/_gbrain`.

Observed result:

```json
{
  "status": "warnings",
  "health_score": 90,
  "brain_checks_score": 100
}
```

Non-ok checks:

| Check | Status | Interpretation |
|---|---|---|
| `retrieval_reflex_health` | `warn` | Policy skill/integration not installed for host repo. Not a Project_R cutover blocker. |
| `connection` | `warn` | DB checks skipped because `--fast` was used. |

`resolver_health` is now `ok`: 52 skills, all reachable.

## Validation

Upstream candidate validation from `reference/gbrain-upstream-0.42.51`:

| Command | Result |
|---|---|
| `bun run typecheck` | Passed |
| `bun test test/check-resolvable.test.ts test/check-resolvable-cli.test.ts test/doctor-behavioral.test.ts test/brain-score-breakdown.test.ts` | 79 pass, 0 fail |
| `bun test test/auth-register-client-args.test.ts test/oauth.test.ts test/brain-allowlist.serial.test.ts test/takes-engine.test.ts test/think-pipeline.serial.test.ts test/ai/gateway-tool-loop.test.ts test/check-resolvable.test.ts test/check-resolvable-cli.test.ts test/doctor-behavioral.test.ts test/brain-score-breakdown.test.ts test/fix-wave-structural.test.ts` | 305 pass, 0 fail, 1183 assertions |
| `bun run build` | Passed |
| Temporary PGLite source-run migration chain | Passed: `init --migrate-only`, `apply-migrations --yes --non-interactive --no-autopilot-install`, idempotent re-run, and `apply-migrations --list` exited 0. |

Project_R backend validation from `backend/`:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

Observed result: 44 passed, 13 warnings.

Full backend validation after final compatibility fixes:

```powershell
.\venv\Scripts\python.exe -m pytest
```

Observed result: 613 passed, 1 skipped, 13 warnings.

The skipped case is the real-project quality fixture source-file validation when Gary's local source sample files are not present in the checkout.

## Upstream Hygiene Fix

The cutover required `patches/gbrain/0.42.51/0008-doctor-resolver-health-windows-crlf.patch`.

Root cause:

- bundled skill frontmatter already had `triggers`, but the local parser only matched LF fences and block arrays;
- on Windows CRLF files, `doctor` misreported missing triggers and returned `resolver_health=fail`;
- `skill-optimizer` existed but lacked a `RESOLVER.md` route;
- several resolver path tests assumed POSIX `/skills` suffixes.

Fix:

- make `parseSkillFrontmatter()` CRLF-safe;
- reuse the shared parser in `check-resolvable`;
- add the `skill-optimizer` resolver row;
- make path-suffix test assertions separator-agnostic.

Additional post-cutover validation required `patches/gbrain/0.42.51/0009-windows-source-run-apply-migrations.patch`.

Root cause:

- several early orchestrator migrations still invoked bare `gbrain ...` subprocesses;
- Project_R runs GBrain from source with `bun run src/cli.ts`, so Windows machines without a global `gbrain` executable could pass service health but fail `apply-migrations`;
- Bun 1.3.14 on Windows also reports an unstable `process.execPath` in some child-process contexts.

Fix:

- add `runGbrainCli([...args])` to resolve the current CLI invocation and fall back through `Bun.which('bun')`;
- migrate v0.12.0, v0.12.2, and v0.13.0 subprocess calls to argv-array `runGbrainCli`;
- update v0.11.0 smoke/install subprocesses to reuse the current CLI;
- add structural regression coverage and a PowerShell temporary PGLite migration-chain validation.

## Rollback

Rollback remains available:

1. Stop the current GBrain serve process.
2. Rename `reference/gbrain-master` aside.
3. Rename `reference/gbrain-master.pre-0.42.51-20260620-124345` back to `reference/gbrain-master`.
4. If runtime rollback is required, replace `backend/workspace_data/_gbrain` with `backend/workspace_data/_gbrain_backup_pre_0.42.51_20260620-124345`.
5. Restart with `.\scripts\start-gbrain.ps1 -Restart`.

Do not delete the backups until Gary has accepted post-upgrade behavior.
