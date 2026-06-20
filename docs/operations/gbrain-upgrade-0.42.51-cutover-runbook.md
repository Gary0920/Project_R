# GBrain 0.42.51 Cutover Runbook

Date: 2026-06-18
Executed: 2026-06-20

This runbook was originally prepared for a guarded cutover. It was executed on 2026-06-20 after `0008-doctor-resolver-health-windows-crlf.patch` fixed the resolver/skill hygiene blocker and `doctor --fast --json` stopped reporting `unhealthy`.

Authoritative execution record: `docs/validation/gbrain-upgrade-0.42.51-cutover.md`.

## Cutover Gate

This gate passed before the 2026-06-20 cutover. For rollback or repeat cutovers, do not execute unless every item below is true:

- `doctor --fast --json` is no longer unhealthy, or Gary explicitly accepts the current warning as non-blocking.
- `reference/gbrain-upstream-0.42.51` is still on `project-r-0.42.51-rebased`.
- `reference/gbrain-upstream-0.42.51/VERSION` is `0.42.51.0`.
- `reference/gbrain-upstream-0.42.51` `HEAD` is `9bf96db807c2f050449142f2f0b05726f58e5054` or a documented Project_R pinned branch commit derived from it.
- Protected path check is empty before cutover.
- `reference/gbrain-master` has been backed up.
- Formal `GBRAIN_HOME` backup strategy has been chosen.
- `.env` secrets will not be edited or printed.
- Rollback steps below have been reviewed.

Protected path check:

```powershell
git status --short -- reference/gbrain-master backend/app.db backend/workspace_data/_gbrain backend/workspace_data/user backend/workspace_data/project backend/workspace_data/customer
```

## Pre-Cutover Validation

From `reference/gbrain-upstream-0.42.51`:

```powershell
git branch --show-current
Get-Content VERSION
git rev-parse HEAD
bun install --frozen-lockfile --ignore-scripts
bun run typecheck
bun test test/auth-register-client-args.test.ts test/oauth.test.ts test/brain-allowlist.serial.test.ts test/takes-engine.test.ts test/think-pipeline.serial.test.ts test/ai/gateway-tool-loop.test.ts
bun run build
```

From `backend`:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

Known caveat resolved on 2026-06-20:

- Windows temp SQLite unlink failures in `tests/conftest.py` were fixed by disposing SQLAlchemy engines before teardown. The Project_R GBrain regression suite now exits 0.

## Backup Plan

Create a timestamped backup root outside the paths being replaced, for example:

```text
reference/_gbrain_backups/YYYYMMDD-HHMMSS/
```

Back up:

- `reference/gbrain-master`
- the chosen formal `GBRAIN_HOME`, currently documented as `backend/workspace_data/_gbrain`
- relevant GBrain manifests if separate from `GBRAIN_HOME`
- non-secret `.env` shape notes only; do not copy API keys into docs

Executed backup paths for the 2026-06-20 cutover:

```text
reference/gbrain-master.pre-0.42.51-20260620-124345
backend/workspace_data/_gbrain_backup_pre_0.42.51_20260620-124345
```

Recommended backup commands for future repeat cutovers, after replacing `<stamp>` manually:

```powershell
$stamp = "<YYYYMMDD-HHMMSS>"
New-Item -ItemType Directory -Force "reference/_gbrain_backups/$stamp" | Out-Null
Copy-Item -Recurse -Force "reference/gbrain-master" "reference/_gbrain_backups/$stamp/gbrain-master"
Copy-Item -Recurse -Force "backend/workspace_data/_gbrain" "reference/_gbrain_backups/$stamp/_gbrain"
```

If `backend/workspace_data/_gbrain` is too large to copy safely, stop and ask Gary for an explicit backup strategy.

## Cutover Plan

The 2026-06-20 cutover has already executed. Only repeat this section after the cutover gate passes.

Recommended strategy for this upgrade is a Project_R fork / pinned branch. The 2026-06-20 local transition replaced `reference/gbrain-master` with the validated `reference/gbrain-upstream-0.42.51` tree.

Short-term local replacement procedure:

```powershell
Rename-Item "reference/gbrain-master" "reference/gbrain-master.pre-0.42.51"
Copy-Item -Recurse -Force "reference/gbrain-upstream-0.42.51" "reference/gbrain-master"
```

After copying:

- Remove transient build/runtime artifacts if they are not part of the chosen vendor strategy.
- Confirm `reference/gbrain-master/VERSION` is `0.42.51.0`.
- Confirm Project_R patch state is documented under `patches/gbrain/0.42.51/`.

## Post-Cutover Validation

From Project_R root:

```powershell
.\scripts\start-gbrain.ps1 -Restart
Invoke-RestMethod http://127.0.0.1:3131/health
```

From `backend`:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

Optional manual smoke must use an explicitly approved workspace/source:

- personal `/query`: `company-wiki` only
- project `/query`: `company-wiki + current project source`
- customer `/query`: customer intelligence only

## Rollback Triggers

Rollback immediately if any of the following happens:

- GBrain service cannot start.
- `/health` does not return a usable status.
- `doctor` shows a new blocker beyond the accepted resolver/skill hygiene issue.
- `/query` fails.
- source scope crosses workspace boundaries.
- citations disappear or become unusable.
- Project_R GBrain-related backend tests show real assertion failures.

## Rollback Procedure

Stop GBrain first if it is running.

```powershell
.\scripts\start-gbrain.ps1 -Stop
```

Restore old GBrain source:

```powershell
Remove-Item -Recurse -Force "reference/gbrain-master"
Rename-Item "reference/gbrain-master.pre-0.42.51" "reference/gbrain-master"
```

If formal `GBRAIN_HOME` was modified and a backup was created:

```powershell
Remove-Item -Recurse -Force "backend/workspace_data/_gbrain"
Copy-Item -Recurse -Force "reference/_gbrain_backups/<stamp>/_gbrain" "backend/workspace_data/_gbrain"
```

Restart old service and verify:

```powershell
.\scripts\start-gbrain.ps1 -Restart
Invoke-RestMethod http://127.0.0.1:3131/health
cd backend
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

## Cutover Record

The 2026-06-20 cutover record is:

```text
docs/validation/gbrain-upgrade-0.42.51-cutover.md
```

Future cutover records must include:

- backup stamp and paths
- exact source commit/version switched in
- exact commands run
- service health result
- Project_R pytest result
- manual smoke result if performed
- rollback readiness
