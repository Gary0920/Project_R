下面是 **GBrain 上游升级适配任务计划**，目标是把 Project_R 当前本地 GBrain `0.41.26.0` 安全升级到上游当前版本 `0.42.51.0`，同时不破坏当前已可用的资料查询链路。

## 任务目标

将 Project_R 的 GBrain 上游依赖从当前本地 `reference/gbrain-master` 的 `0.41.26.0`，升级适配到 `garrytan/gbrain` 上游最新稳定代码。

本任务不直接追求 UI 优化，只处理知识库内核升级、Project_R adapter 兼容、patch 审计、真实查询回归。

## 核心原则

1. 不直接覆盖当前可用的 `reference/gbrain-master`。
2. 不污染当前真实 `GBRAIN_HOME`、真实 brain 数据和当前验收环境。
3. 先在临时目录和临时 `GBRAIN_HOME` 完整验证。
4. 所有本地 patch 必须审计：已被上游吸收则移除，未吸收则重放或改成 adapter 层实现。
5. 升级后必须跑 Project_R 的 source scope、sync、query、think、citation、doctor 回归。
6. 通过后再决定替换 `reference/gbrain-master`，或改成 fork/submodule 管理。

## 当前状态

2026-06-20 已完成本地正式切换：

- `reference/gbrain-master` 当前运行版本：`0.42.51.0`
- `/health` 返回 `status=ok`、`engine=pglite`
- 正式 `backend/workspace_data/_gbrain` 已迁移 schema `107 -> 119`
- `doctor --fast --json` 为 warnings-only：`health_score=90`、`brain_checks_score=100`、`resolver_health=ok`
- 旧源码备份：`reference/gbrain-master.pre-0.42.51-20260620-124345`
- 旧 runtime 备份：`backend/workspace_data/_gbrain_backup_pre_0.42.51_20260620-124345`
- 切换记录：`docs/validation/gbrain-upgrade-0.42.51-cutover.md`

## 原始基线

本地：
- `reference/gbrain-master/VERSION`：升级前为 `0.41.26.0`
- `reference/gbrain-master` 当前不是 Git repo/submodule。
- Project_R 有 9 个本地 GBrain patch：
  - `0001-ollama-local-embedding-limits.patch`
  - `0002-recursive-chunker-local-ollama-cap.patch`
  - `0003-think-source-scope-gather-and-takes.patch`
  - `0004-agent-bound-oauth-client-registration.patch`
  - `0005-subagent-tool-source-scope.patch`
  - `0006-chat-tool-json-schema-wrapper.patch`
  - `0007-think-gather-title-query-variants.patch`
  - `0008-doctor-resolver-health-windows-crlf.patch`
  - `0009-windows-source-run-apply-migrations.patch`

上游：
- GitHub `garrytan/gbrain` 当前 `VERSION`：`0.42.51.0`
- 近期关键变化包括：
  - sync 并发写入瓶颈修复
  - checkpoint 损坏修复
  - `gbrain doctor` 区分正在同步与卡死
  - federated read scope 覆盖 by-slug reads
  - brain-resident skillpacks
  - `gbrain advisor`
  - sync / embed pacing 与成本控制增强

## 2026-06-20 阶段 7-8 状态

阶段 1-6 已完成阶段性验证并形成以下记录：

- `docs/validation/gbrain-upgrade-0.42.51-preaudit.md`
- `docs/validation/gbrain-upgrade-0.42.51-patch-audit.md`
- `docs/validation/gbrain-upgrade-0.42.51-rebase.md`
- `docs/validation/gbrain-upgrade-0.42.51-regression.md`
- `docs/validation/gbrain-upgrade-0.42.51-cutover.md`
- `patches/gbrain/0.42.51/`

阶段 7 已完成切换方案决策：当前推荐 **方案 C：Project_R fork / pinned branch**，因为 `0003`、`0004`、`0005` 仍是 Project_R source scope / agent-bound OAuth / subagent source scope 的关键 patch，不能把后续维护继续依赖散落 patch 文件或直接覆盖上游源码。

阶段 8 已完成本地正式切换。原阻塞点 `doctor --fast --json` 的 upstream resolver/skill hygiene `unhealthy` 已通过 `0008` 修复；后续全面检测发现并通过 `0009` 修复 Windows/source-run `apply-migrations` 依赖全局 `gbrain` 的兼容缺口。切换后 `resolver_health=ok`，剩余 `retrieval_reflex_health` warning 属于 host policy integration 未安装，不阻塞 Project_R 当前 GBrain runtime。

- `docs/validation/gbrain-upgrade-0.42.51-switch-decision.md`
- `docs/operations/gbrain-upgrade-0.42.51-cutover-runbook.md`

## 阶段 1：升级前只读审计

目标：确认当前 Project_R 依赖了哪些 GBrain 能力，避免升级后接口断裂。

检查项：
- `backend/app/features/knowledge/gbrain/adapter.py`
- `backend/app/features/knowledge/gbrain/*`
- `backend/app/features/workspaces/ingest/gbrain_sync.py`
- `scripts/start-gbrain.ps1`
- `backend/scripts/gbrain_*`
- `.env.example` 中所有 `GBRAIN_*`
- `docs/adr/0008-gbrain-upstream-maintenance-policy.md`
- `docs/product/gbrain-feature-inventory.md`
- `docs/milestones/gbrain-adaptation-progress.md`

输出：
- 当前 Project_R 调用的 GBrain CLI / HTTP / MCP 操作清单
- 当前必须保留的 source scope 行为清单
- 当前 patch 与 Project_R 功能的对应关系

验收：
- 不修改代码
- 形成一份 `docs/validation/gbrain-upgrade-0.42.51-preaudit.md`

## 阶段 2：下载上游到隔离目录

目标：获得干净上游源码，不触碰当前 `reference/gbrain-master`。

建议目录：
- `reference/gbrain-upstream-0.42.51/`
或临时：
- `tmp/gbrain-upstream-0.42.51/`

命令方向：
```powershell
git clone https://github.com/garrytan/gbrain reference/gbrain-upstream-0.42.51
cd reference/gbrain-upstream-0.42.51
git checkout master
```

检查：
```powershell
Get-Content VERSION
git rev-parse HEAD
```

验收：
- 上游版本为 `0.42.51.0`
- 新目录是独立 Git repo
- 当前 `reference/gbrain-master` 未变

## 阶段 3：patch 吸收审计

目标：判断 7 个本地 patch 是否仍需要。

逐个审计：

| Patch | 审计目标 |
|---|---|
| `0001` Ollama embedding limits | 上游是否已有 dims / batch cap 配置；若已有，移除 patch |
| `0002` recursive chunker cap | 上游是否已有可配置 chunk cap；优先用 config，不再硬改 |
| `0003` think source scope | 上游 `0.42.46+` 已修 federated read scope，但仍需确认 think gather/search/takes/graph 全链路是否覆盖 |
| `0004` agent-bound OAuth client | 检查上游 OAuth/DCR 是否已有 bound tools/source/slug/budget |
| `0005` subagent source scope | 检查上游 submit_agent / subagent tool 是否继承 OAuth-bound source |
| `0006` AI SDK v6 tool schema/message | 检查上游 gateway loop 是否已兼容当前 DeepSeek / AI SDK |
| `0007` CJK title query variants | 检查上游 search/query expansion 是否已覆盖中文标题式查询 |

操作方式：
```powershell
git apply --check ..\..\patches\gbrain\0001-xxx.patch
```

如果 apply 失败，不能直接认为不需要，必须读相关上游代码确认是“已吸收”还是“冲突”。

输出：
- `docs/validation/gbrain-upgrade-0.42.51-patch-audit.md`
- 每个 patch 标记：
  - `absorbed_by_upstream`
  - `still_required_rebased`
  - `replace_with_config`
  - `replace_with_project_r_adapter`
  - `drop_obsolete`

验收：
- 7 个 patch 都有明确处理结论
- 没有“暂时不知道”的 patch

## 阶段 4：建立临时运行环境

目标：用新 GBrain 跑临时 brain，不碰真实验收数据。

建议环境变量：
```powershell
$env:GBRAIN_CLI_WORKDIR="D:\Gary\System-Building\02-Ongoing\Project_R\reference\gbrain-upstream-0.42.51"
$env:GBRAIN_HOME="D:\Gary\System-Building\02-Ongoing\Project_R\backend\workspace_data\_gbrain_upgrade_test"
$env:GBRAIN_BASE_URL="http://127.0.0.1:3132"
```

原则：
- 不使用当前真实 `backend/workspace_data/_gbrain`
- 不复用当前 `3131` 服务端口
- 不改 `.env`，除非进入最终切换阶段

运行：
```powershell
cd reference/gbrain-upstream-0.42.51
bun install --frozen-lockfile
bun run src/cli.ts doctor
bun run src/cli.ts upgrade
bun run src/cli.ts doctor
```

如果 Windows postinstall 有问题，按现有记录使用：
```powershell
bun install --frozen-lockfile --ignore-scripts
```

验收：
- 临时 GBrain 可启动
- `doctor` 无阻塞错误
- `upgrade` 不影响真实 brain

## 阶段 5：Project_R adapter 兼容测试

目标：确认 Project_R 后端能通过新 GBrain 完成核心调用。

测试内容：
- health
- source status
- source add / ensure
- sync source
- query
- think
- citation normalize
- gap/conflict/warning trace
- source-scoped OAuth client
- admin quality report

优先跑已有测试：
```powershell
cd backend
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_project_sources.py
.\venv\Scripts\python.exe -m pytest tests\test_knowledge_browser.py
```

如果这些测试 mock 较多，需要补真实临时环境 smoke：
```powershell
.\venv\Scripts\python.exe scripts\gbrain_think_regression.py
.\venv\Scripts\python.exe scripts\gbrain_customer_workspace_regression.py
```

验收：
- Project_R adapter 不需要直接依赖 GBrain 内部 DB 表
- `/query` 回答可用
- citation 可被 Project_R 前端消费
- source scope 未串库

## 阶段 6：真实功能回归矩阵

必须覆盖三类工作区：

| 场景 | 预期 |
|---|---|
| 个人工作台 `/query` | 只查 `company-wiki` |
| 项目工作区 `/query` | 查 `company-wiki + 当前项目 source` |
| 客户工作区 `/query` | 只查客户情报 source，不叠加 company/project |
| 普通 Chat | 不自动查 `company-wiki` |
| 员工资料查询 | 不暴露完整 source/file 元数据 |
| 管理员 GBrain 状态 | 可看到 doctor/status/sync/quality |
| 录入闭环 | 文件预处理后进入 gbrain-ready，sync 后可 query 命中 |
| citation | 能回到目标片段或安全摘要 |
| gap/warning | 能进入 context trace 或审核入口 |
| citation-fixer | 管理员入口不报错，权限受控 |
| dream/maintenance | 不自动污染真实数据，只在管理员触发或 worker 配置允许时运行 |

验收输出：
- `docs/validation/gbrain-upgrade-0.42.51-regression.md`
- 每个场景记录：
  - 命令/API
  - 输入 query
  - source scope
  - 返回状态
  - citation 数
  - 是否通过
  - 风险备注

## 阶段 7：切换方案决策

通过临时验证后，有三个可选方案。

### 方案 A：替换 `reference/gbrain-master`

适合：
- patch 大部分已被上游吸收
- Project_R adapter 改动极少
- 不需要长期维护 fork

做法：
- 备份当前 `reference/gbrain-master`
- 用新上游目录替换
- 更新 `docs/product/gbrain-feature-inventory.md` 版本记录
- 更新 `docs/milestones/gbrain-adaptation-progress.md`
- 保留或清理 `patches/gbrain`

优点：
- 简单
- 与现有 `scripts/start-gbrain.ps1` 默认路径兼容

缺点：
- 仍不是 git submodule，后续升级审计较弱

### 方案 B：改成 Git submodule

适合：
- 想长期跟随上游
- patch 已基本移除
- Project_R 只做 adapter，不维护 fork

优点：
- 上游版本可追踪
- 后续升级清晰

缺点：
- Windows / 用户环境需要适配 submodule 初始化
- 对当前项目管理有一次性改造成本

### 方案 C：Project_R fork

适合：
- 多个 patch 仍必须长期存在
- 上游短期不会吸收
- GBrain 是 Project_R 关键内核，需要稳定可控版本

优点：
- patch 管理清晰
- 可发布 Project_R pinned branch

缺点：
- 维护成本最高
- 要定期 rebase upstream

推荐：
- 如果 `0003/0004/0005/0006` 已被上游吸收，优先方案 B。
- 如果仍有关键 patch，优先方案 C。
- 如果只是短期推进内测，方案 A 可以作为过渡，但必须写清版本和 patch 状态。

## 阶段 8：最终切换与回滚

切换前：
- 停止当前 GBrain 服务
- 备份当前：
  - `reference/gbrain-master`
  - 当前 `GBRAIN_HOME`
  - GBrain manifests
  - Project_R `.env`
- 记录当前 commit/hash/version

切换后：
```powershell
.\scripts\start-gbrain.ps1 -Restart
Invoke-RestMethod http://127.0.0.1:3131/health
cd backend
.\venv\Scripts\python.exe -m pytest tests\test_gbrain_project_sources.py tests\test_knowledge_browser.py
```

回滚条件：
- GBrain 服务无法启动
- `doctor` 阻塞错误
- `/query` 不可用
- source scope 出现串库
- citation 丢失或大量异常
- Project_R adapter 大面积失败

回滚方式：
- 停服务
- 恢复旧 `reference/gbrain-master`
- 恢复旧 `GBRAIN_HOME` 或切回旧路径
- 重启服务
- 跑最小 `/query` smoke

## 完成定义

本任务完成必须满足：

- [x] 上游版本、commit、changelog 已记录。
- [x] 8 个 Project_R GBrain patch 都有明确结论。
- [x] 临时 `GBRAIN_HOME` 验证通过。
- [x] Project_R adapter 核心测试通过。
- [x] 个人/项目/客户三类 source scope 回归通过。
- [x] 普通 Chat 不自动查 GBrain 的边界未破坏。
- [ ] 员工侧不暴露过多 GBrain 元数据。（本轮未做前端人工验收；后续 UI 验收保留。）
- [x] 管理员 GBrain 状态/质量/维护入口仍可用。
- [x] 最终采用方案 A/B/C 之一，并记录原因。
- [x] 有明确回滚记录和备份路径。
- [x] 更新相关文档：
  - `docs/product/gbrain-feature-inventory.md`
  - `docs/milestones/gbrain-adaptation-progress.md`
  - `docs/validation/gbrain-upgrade-0.42.51-*.md`
  - 如 patch 状态变化，更新 `patches/gbrain/README.md`

## 推荐执行顺序

1. 先做阶段 1-3：只读审计 + 上游下载 + patch 审计。
2. 如果 patch 冲突很大，暂停，先决定 fork/submodule。
3. 如果 patch 大部分已吸收，继续阶段 4-6。
4. 临时环境全部通过后，再决定最终切换方案。
5. 切换完成后再回到 UI/产品验收。

## 关键风险

- 直接覆盖 `reference/gbrain-master` 会丢失本地 patch。
- 新 GBrain 的 source scope 行为如果和 Project_R adapter 假设不同，可能造成项目/客户资料串库。
- `gbrain upgrade` 可能改变 brain DB/migration 状态，不能先跑在真实 `GBRAIN_HOME`。
- 上游新功能如 advisor、brain-resident skillpack、pacing 很有价值，但不应在升级第一轮就全部产品化。
- Windows 下安装脚本和 postinstall 仍可能需要特殊处理。

我的建议是：下一步先执行 **阶段 1-3**，也就是“只读审计 + 下载上游 + patch 吸收判断”。这一步不影响当前可用系统，做完后我们再决定是走替换、submodule，还是 fork。
