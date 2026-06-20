# GBrain 0.42.51 Upgrade Stage 4-6 Goal

## Objective

恢复并完成当前暂停的 GBrain 0.42.51 阶段 4-6 升级验证，同时把 Project_R 与 GBrain 链路优化纳入本阶段：标准化 6 个 required patch 的 0.42.51 rebased 产物，验证临时 GBrain runtime，不触碰正式 GBrain 数据，并保留 Project_R adapter 的 citation/gap 可见性修复。

Use a token budget of 240000 tokens for this goal.

## Context

- 当前暂停工作已经处于阶段 4-6，不是从零开始。
- Project_R 仓库根目录以当前工作目录为准，不在项目文件中写入本机绝对路径。
- GBrain 上游候选目录：`reference/gbrain-upstream-0.42.51`
- 预期上游基线：
  - `VERSION`: `0.42.51.0`
  - commit: `9bf96db807c2f050449142f2f0b05726f58e5054`
  - branch 可能已经是 `project-r-0.42.51-rebased`
- 已知预审文档可能已经存在：
  - `docs/validation/gbrain-upgrade-0.42.51-preaudit.md`
  - `docs/validation/gbrain-upgrade-0.42.51-patch-audit.md`
- 已知 patch audit 结论：
  - `0001`: required
  - `0002`: required
  - `0003`: required
  - `0004`: required
  - `0005`: required
  - `0006`: absorbed by upstream, keep regression coverage
  - `0007`: required
- 已知 Project_R adapter 优化可能已经部分实现于：
  - `backend/app/features/knowledge/sources.py`

## First Action

先审计当前状态，再决定是否继续：

- 在 Project_R 根目录检查 `git status`。
- 在 `reference/gbrain-upstream-0.42.51` 检查：
  - `git status`
  - 当前 branch
  - `VERSION`
  - `HEAD` commit
- 如果存在，读取并核对：
  - `docs/validation/gbrain-upgrade-0.42.51-preaudit.md`
  - `docs/validation/gbrain-upgrade-0.42.51-patch-audit.md`
- 审计 `backend/app/features/knowledge/sources.py` 当前 diff。
- 报告当前状态是否符合预期的暂停阶段 4-6 状态。
- 如果状态符合预期，从当前改动继续，不重做、不覆盖。
- 如果状态缺失或矛盾，停止并说明具体不匹配的路径和命令输出。

## Scope

### 1. Finish GBrain 0.42.51 rebased patch set

- 保留或重建以下 patch-equivalent changes：
  - `0001` Ollama recipe compatibility
  - `0002` recursive chunker behavior
  - `0003` think/takes pipeline behavior
  - `0004` OAuth/register-client behavior
  - `0005` minion brain allowlist behavior
  - `0007` CJK/title-like think query handling
- 不重新套用 `0006`，如果上游已吸收则仅保留 regression coverage。
- 通过现有 gateway/tool-loop 测试覆盖 `0006` 回归风险。
- 生成或更新 versioned patch artifacts，例如：
  - `patches/gbrain/0.42.51/`
- 更新 `patches/gbrain/README.md` 或相邻 patch index；如果不存在，则创建最小可用索引文档。

### 2. Optimize Project_R and GBrain link contract

- GBrain 继续作为知识引擎；Project_R 不复制 GBrain schema、graph、query、citation-fixer、enrichment 或 think internals。
- Project_R 优化仅限 adapter boundary。
- 审计 `backend/app/features/knowledge/sources.py` 当前修改。
- 保留或精修 adapter 行为：当 GBrain 返回 normalized think citations、gaps、conflicts、warnings 时，Project_R `/query` 回复必须能展示用户可见的引用、缺口和诊断信息。
- 不扩展为大型知识功能重写。
- 保持现有 source-scope contract：
  - personal workspace: `company-wiki` only
  - project workspace: `company-wiki + current project source`
  - customer workspace: customer intelligence only
- 除非现有失败测试证明必要，不修改 UI。

### 3. Embedded GBrain runtime validation contract

- 将 Project_R 使用 GBrain 的方式视为 embedded/dependency mode，而不是 global CLI ownership。
- 如果源码检查显示 `gbrain upgrade` 会修改全局安装、包管理器状态、git checkout、二进制或 ClawHub，不运行 true global/self-upgrade flow。
- 如果跳过 `gbrain upgrade`，在验证文档中记录源码证据和跳过原因。
- runtime 验证只允许使用 `backend/workspace_data/_gbrain_upgrade_test` 下的临时 `GBRAIN_HOME`、`HOME`、`XDG` 路径。
- 如果 GBrain `apply-migrations` 调用裸 `gbrain`，只允许在 `backend/workspace_data/_gbrain_upgrade_test/shim` 内创建临时 `PATH` shim。
- 不把本机绝对 Windows 路径写入项目文件。

## Constraints

- 不触碰或替换 `reference/gbrain-master`。
- 不修改 `backend/app.db`。
- 除只读状态检查外，不读写正式 GBrain 数据目录 `backend/workspace_data/_gbrain`。
- 不修改真实用户、项目、客户资料目录：
  - `backend/workspace_data/user`
  - `backend/workspace_data/project`
  - `backend/workspace_data/customer`
- 不 commit、不 push、不创建 PR。
- 不新增依赖。
- 不主动修改 package lock / bun lock 文件。
- 不在项目文件中硬编码本机绝对路径。
- 不通过改测试、跳过测试或隐藏失败来制造通过。
- Project_R 代码修改仅限升级、patch artifacts、验证文档和 Project_R adapter boundary。

## Validation Commands

### GBrain upstream validation

在 `reference/gbrain-upstream-0.42.51` 运行：

```powershell
bun install --frozen-lockfile
```

如果 Windows postinstall shell redirection 失败，改用并记录结果：

```powershell
bun install --frozen-lockfile --ignore-scripts
```

继续运行：

```powershell
bun run typecheck
bun test test/auth-register-client-args.test.ts test/oauth.test.ts test/brain-allowlist.serial.test.ts test/takes-engine.test.ts test/think-pipeline.serial.test.ts test/ai/gateway-tool-loop.test.ts
bun run build
```

### Temporary GBrain runtime validation

- 仅使用 `backend/workspace_data/_gbrain_upgrade_test`。
- 使用隔离 env 跑 init、doctor、apply-migrations。
- 记录每条命令 exit code。
- 区分 doctor 失败类型：
  - brain data issue
  - resolver/skill hygiene issue
  - patch regression

### Project_R backend validation

在 Project_R 后端运行：

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

如果所有 test assertions 已通过，但 Windows 临时 SQLite unlink 出现 `PermissionError`，记录为 teardown/environment risk；不要改测试来掩盖。

### Protected path check

从 Project_R 根目录运行：

```powershell
git status --short -- reference/gbrain-master backend/app.db backend/workspace_data/_gbrain backend/workspace_data/user backend/workspace_data/project backend/workspace_data/customer
```

结果必须为空。

## Documentation Deliverables

更新或创建：

- `docs/validation/gbrain-upgrade-0.42.51-rebase.md`
- `docs/validation/gbrain-upgrade-0.42.51-regression.md`

文档必须包含：

- upstream version、commit、branch、patch list
- 哪些 patch 被 rebased、absorbed、skipped
- 精确验证命令和结果
- 临时 GBrain runtime path policy
- `gbrain upgrade` 被运行或跳过的原因
- Project_R 与 GBrain adapter 优化总结
- stage 7-8 go/no-go recommendation

## Done When

1. `patches/gbrain/0.42.51/` 或等价 versioned folder 中存在 0.42.51 rebased patch artifacts。
2. patch index 文档列出 `0001`、`0002`、`0003`、`0004`、`0005`、`0006`、`0007` 的最终状态。
3. `0006` 明确标记为 upstream absorbed，并保留 regression coverage 说明。
4. GBrain typecheck、selected patch tests、build 的命令和结果被记录。
5. 临时 GBrain init、doctor、apply-migrations 的命令、exit code 和结论被记录，且未触碰正式数据。
6. Project_R backend GBrain-related pytest 结果被记录。
7. Project_R adapter 能把 normalized GBrain think output 中的 citation、gap、warning/conflict 信息呈现在 `/query` 用户可见回复中。
8. protected path check 输出为空。
9. `docs/validation/gbrain-upgrade-0.42.51-rebase.md` 完成。
10. `docs/validation/gbrain-upgrade-0.42.51-regression.md` 完成。
11. 最终回复给出 stage 7-8 go/no-go recommendation，并列出仍阻塞的精确原因；如果无阻塞，明确说明可进入下一阶段。

## Stop If

- `reference/gbrain-upstream-0.42.51` 的 `VERSION` 或 `HEAD` commit 与预期 0.42.51 基线不一致，且没有清晰解释。
- protected path check 出现任何修改。
- 任一 required patch 无法用 0.42.51 源码行为证据映射。
- 验证需要修改真实 user/project/customer 数据。
- `gbrain upgrade` 会修改全局安装、git remote state、包管理器状态或临时验证区之外的二进制。
- Project_R backend 测试出现真实 assertion failures。
- 继续修复需要大范围架构重写，超出 Project_R 与 GBrain adapter boundary。
- 需要新增依赖、升级语言版本或主动改 lock file。
- 现有测试开始失败；不要通过编辑测试、添加 skip/xfail、注释 case 来解决。
