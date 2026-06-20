# GBrain 0.42.51 Upgrade Stage 7-8 Goal

## Status Update 2026-06-20

This goal has been executed and superseded by the formal cutover record.

- `0008-doctor-resolver-health-windows-crlf.patch` fixed the upstream resolver/skill hygiene blocker on Windows.
- `doctor --fast --json` is no longer `unhealthy`; post-cutover result is `status=warnings`, `resolver_health=ok`, `health_score=90`.
- `reference/gbrain-master` now points to validated GBrain `0.42.51.0`.
- Authoritative record: `docs/validation/gbrain-upgrade-0.42.51-cutover.md`.

The original goal text below is retained as historical execution context.

## Objective

完成 GBrain 0.42.51 后续阶段：基于阶段 1-6 的验证证据做切换方案决策，准备可回滚的最终切换方案；只有在 `doctor` resolver/skill hygiene 风险被明确接受或解决后，才执行正式 `reference/gbrain-master` 切换。

Use a token budget of 200000 tokens for this goal.

## Context

阶段 1-6 已完成，当前证据文件：

- `docs/validation/gbrain-upgrade-0.42.51-preaudit.md`
- `docs/validation/gbrain-upgrade-0.42.51-patch-audit.md`
- `docs/validation/gbrain-upgrade-0.42.51-rebase.md`
- `docs/validation/gbrain-upgrade-0.42.51-regression.md`
- `patches/gbrain/0.42.51/README.md`
- `docs/milestones/Project_R 开发流程V2.3_Gbrain升级.md`

已知结论：

- 上游候选：`reference/gbrain-upstream-0.42.51`
- 版本：`0.42.51.0`
- commit：`9bf96db807c2f050449142f2f0b05726f58e5054`
- rebase branch：`project-r-0.42.51-rebased`
- `0001`、`0002`、`0003`、`0004`、`0005` 已 rebased。
- `0006` 已被 upstream absorbed，保留 gateway loop regression。
- `0007` 已 rebased，但与 `0003` 在 `src/core/think/gather.ts` 有 logical overlap。
- GBrain typecheck、selected patch tests、build 已通过。
- 临时 `init` 和 `apply-migrations --yes` 已通过。
- `doctor --fast --json` 仍为 `unhealthy`，但 `brain_checks_score=100`，失败归类为 upstream resolver/skill hygiene，不是 patch regression。
- Project_R 后端 44 项 GBrain 相关测试断言已通过，但 pytest 最后因 Windows 临时 SQLite unlink `PermissionError` 退出 1。

## First Action

先读取并核对以下文件，再报告当前阶段 7-8 入口状态：

- `docs/validation/gbrain-upgrade-0.42.51-rebase.md`
- `docs/validation/gbrain-upgrade-0.42.51-regression.md`
- `patches/gbrain/0.42.51/README.md`
- `docs/milestones/Project_R 开发流程V2.3_Gbrain升级.md`
- `docs/adr/0008-gbrain-upstream-maintenance-policy.md`

报告：

- 当前是否满足进入阶段 7 的条件。
- `doctor` unhealthy 是否仍未被接受或修复。
- 推荐采用方案 A、B、C 中哪一个。
- 是否允许进入正式切换；如果不允许，只生成决策文档和回滚 runbook，不替换 `reference/gbrain-master`。

## Scope

### 1. Stage 7 switch decision

基于阶段 1-6 证据选择方案：

- 方案 A：替换 `reference/gbrain-master`
- 方案 B：改成 Git submodule
- 方案 C：Project_R fork / pinned branch

当前默认推荐：

- 如果仍有 `0003`、`0004`、`0005` 这类 source-scope / agent-bound / subagent source patch，优先方案 C。
- 如果 Gary 明确只想短期内测推进，可将方案 A 作为过渡，但必须保留旧版本备份和 rollback path。
- 不建议在未解决或未接受 `doctor` unhealthy 的情况下做正式替换。

### 2. Stage 8 guarded cutover

只有满足 cutover gate 才能执行正式切换。

Cutover gate:

- Gary 明确接受 `doctor` resolver/skill hygiene unhealthy 为非阻塞，或先修复到 `doctor --fast --json` 不再 unhealthy。
- protected path check 在切换前为空。
- 旧 `reference/gbrain-master` 已备份。
- 当前正式 `GBRAIN_HOME` 已备份或明确记录不触碰。
- 当前 `.env` / `backend/.env.example` 差异已审计，不写入真实 key。
- 回滚命令和验证命令已写入 runbook。

如果 cutover gate 不满足，本 goal 只产出决策文档和 runbook，不执行替换。

### 3. Documentation updates

创建或更新：

- `docs/validation/gbrain-upgrade-0.42.51-switch-decision.md`
- `docs/operations/gbrain-upgrade-0.42.51-cutover-runbook.md`
- `docs/product/gbrain-feature-inventory.md`
- `docs/milestones/gbrain-adaptation-progress.md`
- `docs/milestones/Project_R 开发流程V2.3_Gbrain升级.md`

如实际执行切换，还必须追加：

- `docs/validation/gbrain-upgrade-0.42.51-cutover.md`

## Constraints

- 不 commit、不 push、不创建 PR。
- 不新增依赖。
- 不修改真实 API key 或 `.env` 密钥。
- 不修改 `backend/app.db`。
- 不删除或覆盖旧 `reference/gbrain-master`，除非已创建备份并写入 runbook。
- 不修改 `backend/workspace_data/user`、`backend/workspace_data/project`、`backend/workspace_data/customer`。
- 不在正式 `backend/workspace_data/_gbrain` 上运行 migration、sync、doctor fix 或 destructive command，除非 cutover gate 满足且 runbook 明确要求。
- 不把本机绝对路径写进项目文件；文档中使用相对路径。
- 不通过编辑测试、skip、xfail 或注释 case 来制造通过。
- 不把 GBrain 内部 schema/query/graph/citation-fixer/enrichment 逻辑迁移到 Project_R。
- Project_R 与 GBrain 链路优化仍限定在 adapter boundary。

## Validation Commands

### Pre-cutover checks

From Project_R root:

```powershell
git status --short
git status --short -- reference/gbrain-master backend/app.db backend/workspace_data/_gbrain backend/workspace_data/user backend/workspace_data/project backend/workspace_data/customer
```

From `reference/gbrain-upstream-0.42.51`:

```powershell
git branch --show-current
Get-Content VERSION
git rev-parse HEAD
bun run typecheck
bun test test/auth-register-client-args.test.ts test/oauth.test.ts test/brain-allowlist.serial.test.ts test/takes-engine.test.ts test/think-pipeline.serial.test.ts test/ai/gateway-tool-loop.test.ts
bun run build
```

From `backend`:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

### Post-cutover checks

Only run if cutover gate is satisfied and actual switch happens.

From Project_R root:

```powershell
.\scripts\start-gbrain.ps1 -Restart
Invoke-RestMethod http://127.0.0.1:3131/health
```

From `backend`:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

If a manual `/query` smoke is required, use a test-only or explicitly approved workspace/source. Do not mutate real customer/project/user 자료 silently.

## Done When

1. `docs/validation/gbrain-upgrade-0.42.51-switch-decision.md` exists and cites the evidence for choosing A/B/C.
2. `docs/operations/gbrain-upgrade-0.42.51-cutover-runbook.md` exists and contains backup, cutover, post-cutover validation, and rollback steps.
3. `docs/product/gbrain-feature-inventory.md` records the `0.42.51.0` candidate status and remaining risk.
4. `docs/milestones/gbrain-adaptation-progress.md` records stage 7 decision and whether stage 8 was executed or deferred.
5. `docs/milestones/Project_R 开发流程V2.3_Gbrain升级.md` reflects stage 7-8 status without marking unverified items complete.
6. If cutover gate is not satisfied, no formal `reference/gbrain-master` replacement occurs and final summary says stage 8 is deferred.
7. If cutover gate is satisfied and switch is executed, `docs/validation/gbrain-upgrade-0.42.51-cutover.md` records exact commands, backup locations, health result, Project_R pytest result, and rollback readiness.
8. Protected path check is empty before any formal cutover and recorded after the goal.
9. Final response gives a clear go/no-go for production use and exact remaining blockers.

## Stop If

- `doctor --fast --json` remains unhealthy and Gary has not explicitly accepted it as non-blocking.
- protected path check shows modifications before cutover.
- The old `reference/gbrain-master` cannot be backed up safely.
- The proposed switch would require editing real `.env` secrets.
- Validation requires mutating `backend/app.db` or real user/project/customer data without explicit authorization.
- `reference/gbrain-upstream-0.42.51` no longer matches `VERSION=0.42.51.0` and commit `9bf96db807c2f050449142f2f0b05726f58e5054`, with no documented reason.
- The selected strategy requires new dependencies, submodule conversion, or fork remote operations that Gary has not approved.
- Any existing related test shows a real assertion failure; do not fix by editing tests, skip, xfail, or comment-out.
- Continuing would require broad architecture changes outside the Project_R adapter boundary.
