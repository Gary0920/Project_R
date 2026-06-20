# GBrain 0.42.51 patch 吸收审计

生成日期：2026-06-18

## 上游版本

| 项目 | 结果 |
|---|---|
| 隔离 Git repo | `reference/gbrain-upstream-0.42.51/` |
| `VERSION` | `0.42.51.0` |
| `git rev-parse HEAD` | `9bf96db807c2f050449142f2f0b05726f58e5054` |
| Clone 方式 | `git clone --depth 1 --filter=blob:none --sparse --branch master` |
| 用户提供 zip 快照 | `reference/gbrain-master-newest/gbrain-master/`，`VERSION=0.42.51.0`，非 Git repo，仅作只读对照备用 |

本轮未运行 `bun install`、`gbrain doctor`、`gbrain sync`、`gbrain upgrade` 或任何真实 GBrain runtime 命令。

## `git apply --check` 结果

| Patch | Exit code | 结果 |
|---|---:|---|
| `0001-ollama-local-embedding-limits.patch` | 0 | 可直接应用到上游 `0.42.51.0`。 |
| `0002-recursive-chunker-local-ollama-cap.patch` | 0 | 可直接应用到上游 `0.42.51.0`。 |
| `0003-think-source-scope-gather-and-takes.patch` | 128 | patch 文件为手写片段，缺少标准 hunk 行号，`git apply` 报 `patch with only garbage at line 4`。 |
| `0004-agent-bound-oauth-client-registration.patch` | 128 | patch 文件为手写片段，缺少标准 hunk 行号，`git apply` 报 `patch with only garbage at line 4`。 |
| `0005-subagent-tool-source-scope.patch` | 128 | patch 文件为手写片段，缺少标准 hunk 行号，`git apply` 报 `patch with only garbage at line 4`。 |
| `0006-chat-tool-json-schema-wrapper.patch` | 128 | patch 文件为手写片段，缺少标准 hunk 行号，`git apply` 报 `patch with only garbage at line 4`。 |
| `0007-think-gather-title-query-variants.patch` | 128 | patch 文件为手写片段，缺少标准 hunk 行号，`git apply` 报 `patch with only garbage at line 4`。 |

`git apply` 失败不直接代表 patch 不需要；以下结论基于上游代码阅读。

## 逐项结论

| Patch | 结论 | 依据 | 升级处理建议 |
|---|---|---|---|
| `0001-ollama-local-embedding-limits.patch` | `still_required_rebased` | 上游 `src/core/ai/recipes/ollama.ts:16-22` 仍只有 `models`、`default_dims=768` 和 `no_batch_cap: true`；未见 `dims_options`、`max_batch_tokens`、`chars_per_token`、`safety_factor`。`src/core/ai/gateway.ts:1398-1401` 的预切分仍依赖 recipe 的 `max_batch_tokens`。 | 仍需重放或改为上游可配置项；短期 rebase patch 最小。 |
| `0002-recursive-chunker-local-ollama-cap.patch` | `still_required_rebased` | 上游 `src/core/chunkers/recursive.ts:50` 注释仍写默认 `6000`，`src/core/chunkers/recursive.ts:75` 仍为 `const maxChars = opts?.maxChars || 6000`。当前 sparse 审计未发现全局配置能按 provider 改默认 cap。 | 仍需重放，或后续把 Project_R 生成的 Markdown / GBrain import 调用改为显式传 `maxChars`；本轮阶段 1-3 不改业务代码。 |
| `0003-think-source-scope-gather-and-takes.patch` | `still_required_rebased` | 上游已有大量 source scope 改进：`src/core/search/hybrid.ts:876-877` 传递 `sourceId/sourceIds`，page reads 与 graph 也支持 source scope；但 `src/core/think/index.ts:268-273` 调 `runGather()` 时没有传 `sourceId/allowedSources`，`src/core/think/gather.ts:110-141` 调 `hybridSearch`、`searchTakes`、`searchTakesVector`、`traversePaths` 均未传 source scope；`src/core/pglite-engine.ts:4300-4340` 的 `searchTakes/searchTakesVector` opts 仍只有 `limit/takesHoldersAllowList`，未过滤 `pages.source_id`；测试 `test/takes-engine.test.ts:94-100` 只覆盖 holder allow-list，没有 source scope 用例。 | 仍需 rebase。上游只部分吸收 federated/page/graph scope，未覆盖 Project_R 最关心的 think gather/takes 全链路。 |
| `0004-agent-bound-oauth-client-registration.patch` | `still_required_rebased` | 上游 `src/core/operations.ts:2889-2999` 已要求并使用 `bound_tools`、`bound_source_id`、`bound_slug_prefixes`、`bound_max_concurrent`、`budget_usd_per_day`，且 `src/core/operations.ts:2981` 会把 `boundSource` 写入 `jobData.source_id`；但 `src/core/oauth-provider.ts:852-898` 的 `registerClientManual()` 仍只插入 `source_id/federated_read`，无 agent binding 参数；`src/commands/auth.ts:351-455` 的 CLI parser 只支持 `--grant-types`、`--scopes`、`--source`、`--federated-read`、`--redirect-uri`、`--token-endpoint-auth-method`，不支持 `--bound-tools` 等参数。 | 上游 submit_agent 运行时已部分吸收，但手动/CLI 注册 agent-bound client 的缺口仍在；Project_R 仍需 rebase 0004，或改用单独的 Project_R adapter DB 写入工具。 |
| `0005-subagent-tool-source-scope.patch` | `still_required_rebased` | 上游 `src/core/operations.ts:2981` 已将 bound source 写入 subagent job data 的 `source_id`；但 `src/core/minions/tools/brain-allowlist.ts:220` 仍硬编码 `sourceId: 'default'`，`src/core/minions/handlers/subagent.ts:243-247` 只传 `brainId: data.brain_id` 给 `buildBrainTools()`，未传 `data.source_id`。 | 仍需 rebase，使 subagent brain tools 继承 OAuth-bound source，而不是落回 `default`。 |
| `0006-chat-tool-json-schema-wrapper.patch` | `absorbed_by_upstream` | 上游 `src/core/ai/gateway.ts:24` 已从 `ai` 导入 `jsonSchema`；`src/core/ai/gateway.ts:2724-2728` 已用 `jsonSchema(t.inputSchema as any)` 包装工具 schema；`src/core/ai/gateway.ts:2339-2362` 已实现 `toModelMessages()`，把 tool-result blocks 转为 AI SDK v6 需要的 `role: 'tool'` 和 structured output；`src/core/ai/gateway.ts:2758` 已在 `generateText()` 前调用 `toModelMessages(opts.messages)`。虽然 `src/core/ai/gateway.ts:3137` 内部仍把 tool results 存成 user message，但发给 SDK 前会转换。 | 不需要重放。可删除 Project_R 侧 0006 patch，后续只保留回归验证 DeepSeek gateway loop。 |
| `0007-think-gather-title-query-variants.patch` | `still_required_rebased` | 上游 `src/core/search/hybrid.ts:301-334` 有 title-phrase boost，`src/core/search/hybrid.ts:1096-1117` 有通用 expansion variants；但 `src/core/think/gather.ts:110-113` 明确 `expansion: false`，且未见 `gatherQuestionVariants`、`MAX_GATHER_QUERY_VARIANTS` 或中文标题式 suffix 剥离逻辑；`src/core/think/gather.ts:110-141` 只用原始 `opts.question`。 | 仍需 rebase，或后续改为 Project_R adapter 在调用 think 前生成更稳定的问题/anchor；本轮不改业务代码。 |

## 汇总

| 状态 | Patch |
|---|---|
| `absorbed_by_upstream` | `0006-chat-tool-json-schema-wrapper.patch` |
| `still_required_rebased` | `0001-ollama-local-embedding-limits.patch`, `0002-recursive-chunker-local-ollama-cap.patch`, `0003-think-source-scope-gather-and-takes.patch`, `0004-agent-bound-oauth-client-registration.patch`, `0005-subagent-tool-source-scope.patch`, `0007-think-gather-title-query-variants.patch` |
| `replace_with_config` | 无 |
| `replace_with_project_r_adapter` | 无 |
| `drop_obsolete` | 无 |

## 阶段 4 前建议

1. 不建议直接进入最终替换或 submodule 切换：7 个 patch 中仍有 6 个需要 rebase，且其中 `0003/0004/0005` 都是 Project_R 防串库和 citation-fixer 权限边界的关键 patch。
2. 下一步若继续阶段 4-6，应先在隔离上游目录创建临时 rebase 分支或 Project_R fork 分支，重放 0001/0002/0003/0004/0005/0007，再用临时 `GBRAIN_HOME` 验证。
3. `0006` 可从后续 patch set 中移除，但必须保留 DeepSeek / AI SDK v6 gateway loop smoke，防止上游回归。
4. 由于 0003-0007 当前 patch 文件不是标准 `git apply` 格式，后续维护前应重新生成标准 patch（含 index 和 hunk 行号）或改为 fork branch，以降低升级成本。
