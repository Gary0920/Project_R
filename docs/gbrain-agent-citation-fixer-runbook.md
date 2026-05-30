# GBrain Agent / Citation-Fixer 运行手册

状态：v0.1，2026-05-30  
适用范围：Project_R 管理员通过 GBrain agent skill 执行 `citation-fixer`、后续知识纠错 agent 和维护型 subagent。

## 当前结论

`citation-fixer` 不是普通 GBrain job，不能用 `submit_job` 执行。它是 GBrain agent skill，Project_R 的正确路径是：

1. 管理员在 Project_R 后台提交 citation-fixer 请求。
2. Project_R 后端用 `GBRAIN_AGENT_*` 取得 GBrain OAuth token。
3. Project_R 调用 GBrain MCP `submit_agent`。
4. GBrain 创建 `subagent` job，由 GBrain worker / inline execution 执行。

这条链路已经有 Project_R adapter、管理员 API、前端表单和测试。本机已注册真实 agent-bound OAuth client，并通过 Project_R adapter -> GBrain MCP `submit_agent` 冒烟验证：GBrain 已接受该 client 的 `agent` scope、工具/source/slug/budget 绑定并创建 subagent job。2026-05-30 又完成 PGLite inline 只读 subagent 烟测：`jobs submit subagent --follow` 能在 `company-wiki` source 内使用 `search/get_page` 和 `deepseek:deepseek-chat` 完成执行。真实 citation-fixer 改写型 subagent 完成执行仍未验收。

## 必要配置

Project_R `.env` 需要：

```env
GBRAIN_AGENT_ENABLED=true
GBRAIN_AGENT_OAUTH_CLIENT_ID=...
GBRAIN_AGENT_OAUTH_CLIENT_SECRET=...
GBRAIN_AGENT_OAUTH_SCOPE=agent
GBRAIN_AGENT_MODEL=deepseek:deepseek-chat
GBRAIN_AGENT_GATEWAY_LOOP_VERIFIED=false
GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED=false
GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=false
GBRAIN_CITATION_FIXER_TOOLS=search,get_page,put_page,list_pages
```

真实跑通过一次 citation-fixer / subagent 后，才能设置：

```env
GBRAIN_AGENT_EXECUTION_VERIFIED=true
```

否则管理员状态应显示 `configured_unverified`，不是 `ready`。

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

Project_R 仍暂不把 citation-fixer 标记为生产就绪，直到完成：

- 用上述命令或未来 GBrain 官方等价入口注册真实 agent-bound OAuth client。（本机已完成）
- 验证 DeepSeek gateway loop，并通过 `submit_agent` 绑定冒烟。（本机已完成）
- 运行 PGLite inline 只读 subagent 烟测，确认 agent 工具调用链能完成执行。（本机已完成）
- 运行真实 citation-fixer / subagent 并确认 job 完成。
- 决定改写型 citation-fixer 暂用受控 PGLite inline 执行，还是切到 Postgres worker 长跑。

## Worker 模式

当前本机 GBrain 使用 PGLite。GBrain 上游说明 persistent worker daemon 需要 Postgres；PGLite 只能使用 inline / follow execution。结果是：

- 管理员提交 `submit_agent` 后，如果没有可执行 worker，任务可能只进入队列而不完成。
- 长期后台 agent / citation-fixer / 自动维护更适合 Postgres worker。
- 在 PGLite 阶段，citation-fixer 只能作为开发验证能力，不能标记为已产品化完成。

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

这只证明 PGLite inline subagent + DeepSeek gateway-loop + 只读工具链可执行，不代表 `citation-fixer` 已获准改写知识页；`GBRAIN_AGENT_EXECUTION_VERIFIED` 仍必须保持 `false`，直到真实 citation-fixer 或等价改写型 subagent 在审核边界内完成验收。

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

截至 2026-05-30，本机预检应进入：

- `status=configured_unverified`
- `gateway_loop_status=verified`
- `binding_status=inline_execution_verified`
- `inline_execution_verified=true`
- `execution_verified=false`
- `worker.mode=inline_only`

剩余未闭环项是：真实 citation-fixer / subagent 改写型任务完成执行，以及 Postgres worker 长跑或 PGLite inline 管理员执行策略。
