# GBrain Agent / Citation-Fixer 运行手册

状态：v0.3，2026-06-02
适用范围：Project_R 管理员通过 GBrain agent skill 执行 `citation-fixer`、后续知识纠错 agent 和维护型 subagent。

## 当前结论

`citation-fixer` 不是普通 GBrain job，不能用 `submit_job` 执行。它是 GBrain agent skill，Project_R 的正确路径是：

1. 管理员在 Project_R 后台提交 citation-fixer 请求。
2. Project_R 后端用 `GBRAIN_AGENT_*` 取得 GBrain OAuth token。
3. Project_R 调用 GBrain MCP `submit_agent`。
4. GBrain 创建 `subagent` job，由 GBrain worker / inline execution 执行。

这条链路已经有 Project_R adapter、管理员 API、前端表单和测试。本机已注册真实 agent-bound OAuth client，并通过 Project_R adapter -> GBrain MCP `submit_agent` 冒烟验证：GBrain 已接受该 client 的 `agent` scope、工具/source/slug/budget 绑定并创建 subagent job。2026-05-30 又完成 PGLite inline 只读 subagent 烟测：`jobs submit subagent --follow` 能在 `company-wiki` source 内使用 `search/get_page` 和 `deepseek:deepseek-chat` 完成执行。2026-06-02 已通过真实改写型 smoke：`backend/scripts/gbrain_agent_citation_fixer_mutation_smoke.py` 创建合成测试页 `reviews/citation-fixer-smoke/project-r-citation-fixer-smoke`，限定 `reviews/citation-fixer-smoke/*` 写入边界，GBrain subagent job `#172` 成功用 `put_page` 把预置坏引用修复为 `[[rules/书面化原则]]`。脚本随后把 GBrain 非 default source 的 `.sources/company-wiki/...` sidecar 同步回 Project_R 正式 `derived/reviews/...` 文件，并在 `derived/` 本地 Git 生成提交 `8a3ace3 Verify Project_R citation-fixer smoke mutation`。因此本机 `GBRAIN_AGENT_EXECUTION_VERIFIED=true` 已成立。同日继续补 Project_R 管理员追踪闭环：`POST /admin/knowledge/gbrain/citation-fixer` 提交后写入 `manifests/gbrain-citation-fixer-jobs.json`，`POST /admin/knowledge/gbrain/citation-fixer/poll-jobs` 轮询 GBrain job，完成时同步 `.sources/company-wiki/...` sidecar 到正式 `derived/`、提交本地 Git、写审计并通知管理员；`core/gbrain_maintenance_worker.py` 也会周期性轮询 citation-fixer tracked jobs，管理员 GBrain 面板显示 tracking 摘要和“轮询引用修复”按钮。随后补齐低分答案审核入口：`POST /admin/knowledge-reviews/{review_id}/citation-fixer` 只接受 `gbrain_answer_correction:*` 审核项，默认从审核内容里的 GBrain 引用列表推断 page slug 和同目录写入边界，提交后复用同一 job tracking / worker poll / sidecar sync 链路；该动作不会自动通过审核项，也不会直接声明事实已修正。随后继续补单任务回滚 MVP：tracking 记录 citation-fixer 同步提交的 Git commit hash，管理员可通过 `POST /admin/knowledge/gbrain/citation-fixer/{job_id}/rollback` 或 GBrain 面板“回滚”按钮撤销该次写入，系统会写审计、通知，并清理回滚时可能恢复的 `.sources` sidecar。

## 必要配置

Project_R `.env` 需要：

```env
GBRAIN_AGENT_ENABLED=true
GBRAIN_AGENT_OAUTH_CLIENT_ID=...
GBRAIN_AGENT_OAUTH_CLIENT_SECRET=...
GBRAIN_AGENT_OAUTH_SCOPE=agent
GBRAIN_AGENT_MODEL=deepseek:deepseek-chat
GBRAIN_AGENT_GATEWAY_LOOP_VERIFIED=true
GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED=true
GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=true
GBRAIN_AGENT_EXECUTION_VERIFIED=true
GBRAIN_CITATION_FIXER_TOOLS=search,get_page,put_page,list_pages
```

只有真实跑通过 citation-fixer / subagent 改写型 smoke 后，才能设置：

```env
GBRAIN_AGENT_EXECUTION_VERIFIED=true
```

否则管理员状态应显示 `configured_unverified`，不是 `ready`。本机已通过 smoke，预检应显示 `ready`；更换 OAuth client、GBrain DB 或 source 后必须重新验收。

## GBrain 侧要求

上游 `submit_agent` operation 要求 OAuth client 具备：

- `agent` scope
- 绑定工具：`search`、`get_page`、`put_page`、`list_pages`
- 绑定 source，例如 `company-wiki`
- 绑定允许写入的 slug prefix，例如 `rules/`、`reviews/`
- 绑定并发上限和每日预算

当前本地 `reference/gbrain-master` 已通过 Project_R patch `patches/gbrain/0004-agent-bound-oauth-client-registration.patch` 补齐 CLI / provider 注册能力，可在 `auth register-client` 时写入 `bound_tools`、`bound_source_id`、`bound_slug_prefixes`、`bound_max_concurrent`、`budget_usd_per_day`。

推荐使用 Project_R 脚本注册，避免把一次性 client secret 打到终端：

```powershell
cd backend
venv\Scripts\python.exe scripts\gbrain_register_agent_client.py
```

该脚本会捕获 GBrain CLI 输出，解析 `Client ID` / `Client Secret`，只把 secret 写入后端 `.env`，终端只显示脱敏结果。新注册 client 后会把 `GBRAIN_AGENT_EXECUTION_VERIFIED=false` 和 `GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED=false` 写回 `.env`，避免沿用旧验收标记。

示例命令：

```powershell
cd reference\gbrain-master
$env:GBRAIN_HOME="..\..\backend\workspace_data\global\company-wiki"
bun run src\commands\auth.ts register-client project-r-citation-fixer `
  --grant-types client_credentials `
  --scopes agent `
  --source company-wiki `
  --federated-read company-wiki `
  --bound-tools search,get_page,put_page,list_pages `
  --bound-source company-wiki `
  --bound-slug-prefixes rules/,reviews/,standards/,meetings/ `
  --bound-max-concurrent 1 `
  --budget-usd-per-day 1
```

该命令会显示一次性 client secret。只允许写入后端 `.env`，不能写进前端、Git 或文档示例明文。

Project_R 仍暂不把 citation-fixer 标记为长期生产自动化完成，直到完成：

- 用上述命令或未来 GBrain 官方等价入口注册真实 agent-bound OAuth client。（本机已完成）
- 验证 DeepSeek gateway loop，并通过 `submit_agent` 绑定冒烟。（本机已完成）
- 运行 PGLite inline 只读 subagent 烟测，确认 agent 工具调用链能完成执行。（本机已完成）
- 真实 citation-fixer / subagent 改写型 smoke 已完成。（本机 job #172）
- 决定正式运营阶段继续使用受控 PGLite inline 管理员执行，还是切到 Postgres worker 长跑。

## Worker 模式

当前本机 GBrain 使用 PGLite。GBrain 上游说明 persistent worker daemon 需要 Postgres；PGLite 只能使用 inline / follow execution。结果是：

- 管理员提交 `submit_agent` 后，如果没有可执行 worker，任务可能只进入队列而不完成。
- 长期后台 agent / citation-fixer / 自动维护更适合 Postgres worker。
- 在 PGLite 阶段，citation-fixer 已完成受控 inline 改写验证；但长期后台 worker、自动批量修复和无人值守维护仍不能标记为产品化完成。

## DeepSeek 与 gateway loop

GBrain subagent 默认偏向 Anthropic tool-use 模式。使用 `deepseek:deepseek-chat` 这类非 Anthropic 模型时，GBrain 侧需要：

```bash
gbrain config set agent.use_gateway_loop true --force
```

确认 GBrain 侧已设置后，再把 Project_R `.env` 中的 `GBRAIN_AGENT_GATEWAY_LOOP_VERIFIED=true` 作为人工验收标记。未设置时，Project_R 会显示 `gateway_loop_status=not_checked`，不能假定 DeepSeek subagent 可以执行。

推荐使用 Project_R 脚本：

```powershell
cd backend
venv\Scripts\python.exe scripts\gbrain_enable_agent_gateway_loop.py
```

GBrain 当前版本没有把 `agent.use_gateway_loop` 放入 `config set` known-key 列表，但 subagent runtime 会读取该 key，因此脚本使用 `--force` 写入，并在成功后更新 `.env` 标记。

## 绑定冒烟验证

注册 client 并启用 gateway loop 后，运行：

```powershell
cd backend
venv\Scripts\python.exe scripts\gbrain_agent_submit_smoke.py
```

该脚本会通过 Project_R adapter 调 GBrain MCP `submit_agent`，默认针对 `rules/书面化原则` 创建一条 citation-fixer subagent job，然后立即取消。它只验证 OAuth scope、工具绑定、source 绑定、slug 前缀和预算绑定被 GBrain 接受，不代表 citation-fixer 已真正执行。成功后写入：

```env
GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED=true
```

## PGLite inline 执行烟测

PGLite 阶段没有持久 worker daemon。可以用只读 inline 烟测验证 subagent 执行链路：

```powershell
cd backend
venv\Scripts\python.exe scripts\gbrain_agent_inline_execution_smoke.py
```

该脚本会临时停止 GBrain HTTP service，调用 GBrain 原生 CLI：

```powershell
bun src\cli.ts jobs submit subagent --follow --max-attempts 1
```

默认只允许 `search,get_page`，mutation disabled，并强制传 `source_id=company-wiki`。成功后写入：

```env
GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=true
```

这只证明 PGLite inline subagent + DeepSeek gateway-loop + 只读工具链可执行，不代表 `citation-fixer` 已获准改写知识页；真实改写能力必须继续通过下一节 mutation smoke 单独验收。

## PGLite citation-fixer 改写型烟测

只读 inline 烟测通过后，使用受控改写脚本验证 `put_page` 能在安全边界内写入：

```powershell
cd backend
venv\Scripts\python.exe scripts\gbrain_agent_citation_fixer_mutation_smoke.py
```

该脚本会：

- 在 `workspace_data/global/company-wiki/derived/reviews/citation-fixer-smoke/project-r-citation-fixer-smoke.md` 写入合成测试页。
- 触发 GBrain sync，使测试页进入 `company-wiki` source。
- 调用 GBrain 原生 `jobs submit subagent --follow`。
- 允许工具为 `search,get_page,put_page,list_pages`。
- 强制 `allowed_slug_prefixes=["reviews/citation-fixer-smoke/*"]`。GBrain 该字段使用 glob 语义，裸 `reviews/citation-fixer-smoke/` 不匹配子页。
- 要求 subagent 只把坏引用标记 `[[BROKEN_CITATION_FIXME]]` 修复为 `[[rules/书面化原则]]`。
- 用 source-scoped DB 探针确认 `Citation:` 行已修正。
- 将 GBrain 写到 `.sources/<source>/...` 的 sidecar 同步回 Project_R 正式 `derived/` 文件，并提交 `derived/` 本地 Git。
- 只有 DB、正式文件和本地 Git 记录都通过时才视为成功。

默认成功后会写入：

```env
GBRAIN_AGENT_EXECUTION_VERIFIED=true
GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=true
```

如果只想准备测试页并打印参数，不执行 subagent：

```powershell
cd backend
venv\Scripts\python.exe scripts\gbrain_agent_citation_fixer_mutation_smoke.py --dry-run --no-env-update
```

如果真实执行失败，不得手工把 `GBRAIN_AGENT_EXECUTION_VERIFIED` 改成 true；应保留失败输出并继续排查 GBrain worker / gateway loop / OAuth binding / slug glob / PGLite 初始化。

## 预检

运行：

```powershell
cd backend
venv\Scripts\python.exe scripts\gbrain_agent_preflight.py
```

严格模式：

```powershell
cd backend
venv\Scripts\python.exe scripts\gbrain_agent_preflight.py --strict
```

该脚本不打印 OAuth secret，只检查 Project_R 配置、citation-fixer 工具列表、执行验收标记和 GBrain engine / worker 模式。

截至 2026-06-02，本机预检应进入：

- `status=ready`
- `gateway_loop_status=verified`
- `binding_status=execution_verified`
- `inline_execution_verified=true`
- `execution_verified=true`
- `worker.mode=inline_only`

剩余未闭环项是：GBrain 原生 Postgres worker 长跑或更明确的 PGLite inline 管理员执行策略、批量 citation-fixer 费用/权限边界、批量/冲突状态下的复杂恢复策略，以及是否允许低分反馈审核自动串到 citation-fixer 的产品决策。当前已支持低分审核项管理员受控触发和单任务 Git 回滚，不做无人审核的自动修正。
