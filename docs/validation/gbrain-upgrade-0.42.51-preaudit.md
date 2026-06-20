# GBrain 0.42.51 升级前只读审计

生成日期：2026-06-18

## 审计范围

本轮只覆盖 `docs/milestones/Project_R 开发流程V2.3_Gbrain升级.md` 的阶段 1：确认 Project_R 当前依赖的 GBrain 能力、source scope 边界和本地 patch 对应关系。未运行 GBrain `doctor`、`sync`、`upgrade` 或真实查询回归，未修改业务代码、`.env`、真实 `GBRAIN_HOME`、真实 workspace 数据或 `reference/gbrain-master`。

已读取的核心文件：

- `docs/milestones/Project_R 开发流程V2.3_Gbrain升级.md`
- `AGENTS.md`
- `backend/app/features/knowledge/gbrain/adapter.py`
- `backend/app/features/workspaces/ingest/gbrain_sync.py`
- `scripts/start-gbrain.ps1`
- `backend/.env.example`
- `docs/adr/0008-gbrain-upstream-maintenance-policy.md`
- `docs/product/gbrain-feature-inventory.md`
- `docs/milestones/gbrain-adaptation-progress.md`
- `patches/gbrain/*.patch`

## First action 计数

| 项目 | 结果 |
|---|---:|
| 计划文件阶段数 | 8 |
| GBrain 调用点行级初筛命中 | 349 |
| 去重后的 MCP tool 名称 | 24 |
| patch 文件数 | 7 |
| AGENTS.md 中真实数据 / GBrain / 验证 / 禁止项关键约束行 | 39 |

说明：计划文件写 `.env.example`，当前仓库实际 GBrain 示例配置位于 `backend/.env.example`。

## 当前 Project_R 调用的 GBrain 操作清单

### HTTP / OAuth / MCP

| 操作 | Project_R 入口 | GBrain 侧入口 | 用途 |
|---|---|---|---|
| 服务健康检查 | `GBrainAdapter._probe_service_health()` / `health()` | `GET /health` | 管理员状态、启动后健康探测。 |
| MCP JSON-RPC | `GBrainAdapter._call_mcp_tool()` | `POST /mcp` | 统一调用 query、think、sources、jobs、schema、graph 等能力。 |
| OAuth token | `GBrainAdapter._request_oauth_token()` | `POST /token` | Think / agent 的 source-scoped OAuth client_credentials。 |

### MCP tools

当前 adapter 直接调用的 GBrain MCP tools：

| 类别 | tools |
|---|---|
| Source / sync | `sources_list`, `sources_status`, `sync_brain` |
| Query / Think | `query`, `think` |
| Page / graph / timeline | `get_page`, `traverse_graph`, `get_timeline`, `get_backlinks` |
| Admin / doctor | `run_doctor`, `get_status_snapshot`, `run_onboard` |
| Jobs | `list_jobs`, `get_job`, `get_job_progress`, `submit_job`, `cancel_job`, `retry_job` |
| Agent / citation-fixer | `submit_agent` |
| Contradiction | `find_contradictions` |
| Schema | `get_active_schema_pack`, `schema_stats`, `schema_graph`, `schema_review_orphans` |

### CLI / process

| 操作 | Project_R 入口 | GBrain 命令形态 | 风险边界 |
|---|---|---|---|
| 启动 HTTP/MCP 服务 | `scripts/start-gbrain.ps1`, `GBrainAdapter.start_http_service()` | `bun src/cli.ts serve --http --port <port> --bind <bind> --suppress-bootstrap-token` | 会写服务 manifest/log 到 `GBRAIN_HOME/manifests`；本轮未运行。 |
| 停止服务 | `GBrainAdapter.stop_http_service()` / `adapter_utils` | PowerShell / process PID 探测 | 仅用于运行期互斥；本轮未运行。 |
| Source sync fallback | `GBrainAdapter.sync_source()` -> `_sync_source_via_cli()` | `bun src/cli.ts sync --source <source_id> [--full] [--no-pull] [--no-embed]` | 会写 GBrain runtime；阶段 1-3 禁止运行。 |
| Think client 注册 | `GBrainAdapter.ensure_think_source_client()` | `bun src/cli.ts auth register-client ... --source <source> --federated-read <source>` | 会写 OAuth client 到 GBrain runtime；本轮未运行。 |
| Agent client 注册脚本 | `backend/scripts/gbrain_register_agent_client.py` | `auth register-client` + agent binding flags | 会改 GBrain runtime / `.env`；本轮只读。 |
| Gateway loop 配置脚本 | `backend/scripts/gbrain_enable_agent_gateway_loop.py` | `gbrain config set agent.use_gateway_loop true --force` | 会改 GBrain config / `.env`；本轮只读。 |
| Subagent smoke | `backend/scripts/gbrain_agent_*_smoke.py` | `jobs submit subagent --follow` 或 Project_R adapter `submit_agent` | 会提交 job / 可能写 sidecar；本轮只读。 |
| Contradiction probe | `app/features/knowledge/gbrain/maintenance/contradiction_probe.py` | `eval suspected-contradictions run --queries-file ... --json --yes` | 会读 GBrain runtime，并可能重启服务；本轮只读。 |

## 当前必须保留的 source scope 行为

| 场景 | 必须保留的行为 | 证据 |
|---|---|---|
| 个人工作台 `/query` | 只查询 `company-wiki`，不得查询项目或客户 source。 | `AGENTS.md` `/query Source Scope`；`docs/milestones/gbrain-adaptation-progress.md` 2026-06-04 决策。 |
| 项目工作区 `/query` | 查询 `company-wiki + 当前项目 source`，项目特有资料不得串到其他项目。 | `AGENTS.md` `/query Source Scope`；`GBrainAdapter.ensure_project_source()` / `sync_project_source()`；`sync_workspace_gbrain_source()`。 |
| 客户工作区 `/query` | 只查询客户情报 source，不叠加 `company-wiki` 或项目 source。 | `AGENTS.md` 客户情报规则；`customer_source_id_for_workspace()` / `ensure_customer_source()` / `sync_customer_source()`。 |
| Think | `GBRAIN_THINK_SOURCE_SCOPE_VERIFIED=true` 后才可把 GBrain native think 作为 `/query` 回答层；project/customer source 通过 per-source OAuth client 或允许列表控制。 | `backend/.env.example` Think 配置；`GBrainAdapter.think()` / `ensure_think_source_client()`。 |
| Agent / citation-fixer | agent client 必须绑定 tools/source/slug/budget；未真实执行验收前不得显示 ready。 | `backend/.env.example` Agent 配置；`GBrainAdapter.agent_status()` / `submit_citation_fixer()`。 |
| 原始文件与 GBrain-ready | 用户源文件目录只保存原始文件；GBrain-ready 写入 `_preprocessed/.../gbrain-ready/`，不在源文件目录新增 `derived/`。 | `AGENTS.md` GBrain 边界；`resolve_gbrain_source_paths()`。 |
| 普通 Chat | 普通 Chat 不自动查 GBrain；知识库查询必须显式 `/query` 或等价知识库 Skill。 | `AGENTS.md` 前端约定；`docs/product/gbrain-feature-inventory.md`。 |

## 当前 patch 与 Project_R 功能对应关系

| Patch | 对应 Project_R 功能 | 继续升级审计重点 |
|---|---|---|
| `0001-ollama-local-embedding-limits.patch` | 本地 Ollama + `mxbai-embed-large` embedding 的固定维度和保守 batch cap，避免 PDF/中文长页 embedding 请求过大。 | 上游 recipe 是否已有 `dims_options`、`max_batch_tokens`、`chars_per_token` 或等效 provider 配置。 |
| `0002-recursive-chunker-local-ollama-cap.patch` | 将 recursive chunker 默认 `maxChars` 从 6000 降到 400，以适配本地 Ollama dense CJK/标准文档。 | 上游是否已有按 provider / config 调整 chunk cap 的能力；优先配置化，不再硬改默认。 |
| `0003-think-source-scope-gather-and-takes.patch` | Think gather/search/takes/graph 全链路传递 `sourceId/allowedSources`，防止项目/客户 source 串库。 | 上游 `0.42.46+` federated read scope 是否已覆盖 page、take、vector take、graph。 |
| `0004-agent-bound-oauth-client-registration.patch` | 允许 CLI 注册 agent-bound OAuth client，写入工具、source、slug prefix、并发和预算绑定，用于 citation-fixer/subagent。 | 上游 OAuth/DCR/CLI 是否原生支持 bound tools/source/slug/budget。 |
| `0005-subagent-tool-source-scope.patch` | subagent brain tools 继承 OAuth-bound source id，避免 `search/get_page/put_page` 默认落到 `default`。 | 上游 `submit_agent` / minion tool context 是否已传递 bound source。 |
| `0006-chat-tool-json-schema-wrapper.patch` | DeepSeek / AI SDK v6 gateway loop：用 `jsonSchema()` 包 provider-neutral schema，并把 tool result 作为 AI SDK tool messages 回传。 | 上游 gateway 是否已兼容 AI SDK v6 tool schema 和 tool-result 消息格式。 |
| `0007-think-gather-title-query-variants.patch` | 对中文标题式问题生成保守 query variants，让“书面化原则是什么”等问题命中 exact title page。 | 上游 gather/search/query expansion 是否已有 CJK 标题式查询归一化。 |

## 风险与阶段边界

- 阶段 1 只读审计没有验证上游 `0.42.51.0` 是否吸收这些 patch；该判断进入 `gbrain-upgrade-0.42.51-patch-audit.md`。
- 阶段 1 没有运行任何会写 `GBRAIN_HOME` 的命令。
- 后续阶段 2 只允许 clone 到 `reference/gbrain-upstream-0.42.51/` 并读取 `VERSION` / commit。
- 后续阶段 3 允许对隔离上游目录运行 `git apply --check`，但结论必须基于代码阅读，不能只看 apply 结果。
