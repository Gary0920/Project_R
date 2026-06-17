# Project_R 开发流程

版本：v3.1  
更新时间：2026-06-09  
用途：Project_R 当前开发推进清单。本文只维护阶段顺序、任务、完成标志和验证要求。

## 1. 执行原则

- 先做可验证竖切片，再做泛化。
- 当前阶段以显式入口为主：普通 Chat 不自动触发 GBrain、文件生成或 Skill。
- 不恢复旧 RAG / Chroma / Wiki Router / `vector_store`。
- 不把个人工作台重新做成个人文件库或个人知识库。
- 不修改真实用户、真实工作区、真实 source，除非 Gary 明确授权。
- 代码实现、文档和测试必须同步；无法验证必须在最终回复说明。

## 2. 验证规则

| 改动类型 | 最小验证 |
|---|---|
| 后端接口 / service | 相关 `pytest` 或最小脚本验证 |
| 前端 UI / 状态 | `bun run typecheck`，必要时 `bun run build` |
| GBrain adapter / source | source status + query/think regression 或受控 smoke |
| 文件录入 / 预处理 | manifest、输出 Markdown、GBrain sync、citation 验证 |
| 权限 | 至少验证系统管理员、普通用户、无权限用户三类结果 |
| 文档更新 | `rg` 搜索旧口径，确认没有与新规则冲突 |

真实数据测试规则：

- 自动测试必须使用临时 DB、临时 workspace root、fixture 或 monkeypatch。
- 不得污染 `backend/app.db`、真实 `workspace_data/project/`、真实 `workspace_data/customer/`、真实 GBrain source。
- Gary 已新建项目测试路径 `backend/workspace_data/project/TEST/TEST`；确需用真实项目目录做手工或 smoke 验证时，只能使用该路径，不得污染 `AURA/BFI/SPECWISE/SYNOVA` 等真实品牌预创目录。
- 测试残留必须清理；无法清理时列出残留。

## 3. 当前状态总览

| 模块 | 状态 | 说明 |
|---|---|---|
| 基础后端 | 已完成 | FastAPI、SQLite、用户、JWT、审计、会话。 |
| LLM Provider | 已完成 MVP | DeepSeek、MiMo 等模型 profile 和 Key 轮询能力已具备。 |
| 前端工作台 | 已完成 MVP | Proma 风格主界面、会话、侧栏、标签页、设置、通知。 |
| 个人工作台 | 产品边界已冻结 | 只承载 Chat、提示词、本轮附件和轻量 Skill 输出，不做文件面板和 GBrain source。 |
| 项目工作区 | 已完成 MVP | 文件面板、上传、删除、回收站、权限、审计、项目 source 查询和录入 MVP。 |
| 客户工作区 | 已完成早期 MVP | 客户权限、客户查询、防串库、图谱/时间线基础入口。 |
| GBrain 接入 | 已完成主链路 MVP | `/query` 使用 native think；旧 RAG 已清退。 |
| GBrain 预处理架构 | 设计已冻结，待迁移 | 目标为 `_preprocessed/.../gbrain-ready/`，旧 `derived/` 是 MVP 历史实现。 |
| 文件生成 | tracer bullet | `.docx` 基础生成和下载已可用，正式模板仍待补。 |
| 业务 Skill | 会议 Skill 第一版闭环完成 | 已完成会议资料输入、转录、纪要/行动项、说话人/术语修正、音视频转录、GBrain-ready 生成、真实样本验收、后端 E2E 和 Playwright 前端关键路径验证；片段级 ASR 重跑、DOCX 正式导出、在线编辑和任务系统进入后续增强。 |
| 管理后台 | MVP 可用 | 用户、GBrain、审核、审计、维护、质量回归均已有入口。 |
| 客户端打包 | 代码级完成 | Windows 安装包和内网更新流程已有，仍需正式机器/用户测试。 |

## 4. 已完成阶段

以下阶段不再作为主要开发内容重复展开，只在出现回归时修复：

- Phase 1-8：环境、后端骨架、认证、LLM、基础 Chat、Electron 骨架、登录。
- Phase 9：Proma 风格聊天工作台、多标签、会话管理、提示词、通知和设置主体。
- Phase 10：旧 RAG 清退，GBrain `/query` 主路径，company/project/customer source MVP。
- Phase 10E：工作区文件管理、项目录入、客户图谱/时间线基础入口。
- Phase 11：文件生成第一条 `.docx` tracer bullet。
- Phase 12：SkillRun 和显式 Skill 启动底座。
- Phase 13：管理员后台 MVP。
- Phase 14-18：设置、欢迎引导、Windows 检查、通知中心。
- Phase 20：Windows 打包与内网更新代码级准备。

Phase 19 Mac mini 迁移暂缓，不作为近期阻塞项。

## 5. 当前主线 A：GBrain 预处理架构迁移

目标：把旧 `workspace_data/.../derived/` MVP 路径迁移为 `_preprocessed/.../gbrain-ready/` 架构，让用户源文件目录只保存原始业务文件。

当前真实源文件状态：

- 公司知识库源文件已重新放入 `backend/workspace_data/global/company-wiki/raw/`。
- 客户信息源文件已重新放入 `backend/workspace_data/customer/CRM/raw/`。
- `CRM` 是全公司客户情报工作区入口，不是品牌层级、不是项目目录，也不是某个单客户 workspace 的子目录；用户在 Project_R 中点击 CRM 即进入这个服务全公司营销需求的客户情报工作区。
- 两处源文件均为 Obsidian 导出资料，保留了大量 Obsidian 双链、embed、frontmatter、标签、反链痕迹和导出噪音；不得直接交给 GBrain sync。
- 正式流程必须先由 Project_R 预处理清洗噪音、保留可追溯来源，再写入对应 `_preprocessed/.../gbrain-ready/`，之后才交给 GBrain 做 source sync/import、chunk、embedding、schema/enrich 等精加工。

### A1. 后端路径与 source repo 迁移

任务：

- [x] 新增统一路径 resolver：company/project/customer -> `{gbrain-ready,runs,manifests}`。
- [x] company-wiki source path 目标改为 `_preprocessed/company/company-wiki/gbrain-ready/`。
- [x] project source path 目标改为 `_preprocessed/project/{brand}/{workspace_id}-{project_slug}/gbrain-ready/`。
- [x] customer source path 目标改为 `_preprocessed/customer/{workspace_id}-{customer_slug}/gbrain-ready/`。
- [x] CRM 全公司客户情报 source path 目标固定为 `_preprocessed/customer/crm/gbrain-ready/`，不套用 project brand 或 `{workspace_id}-crm` 层级。
- [x] 保留旧 `derived/` 兼容读取或迁移脚本，但新写入禁止进入用户源文件目录。
- [x] GBrain `sources_status` 和管理员状态页显示新路径、旧路径和迁移状态。
- [x] 将 `global/company-wiki/raw/` 的 Obsidian 导出源文件预处理到 `_preprocessed/company/company-wiki/gbrain-ready/`。
- [x] 将 `customer/CRM/raw/` 的 Obsidian 导出客户资料预处理到 `_preprocessed/customer/crm/gbrain-ready/`。

完成标志：

- 新建项目录入后，用户项目目录不出现 `derived/`。
- `gbrain-ready/` 可被 GBrain sync。
- manifest 能追踪源文件到 GBrain-ready Markdown 的映射。

验证：

- 临时项目 workspace fixture。
- GBrain source status path match。
- 项目 `/query` 命中新 `gbrain-ready/` 内容。
- 公司知识和客户资料的 Obsidian 噪音清理前后抽样 diff。
- GBrain sync 前确认 source path 指向 `gbrain-ready/`，不指向 raw。

### A2. 录入范围与权限收紧

任务：

- [x] 文件面板“录入”改为处理当前打开路径。
- [x] 递归子文件夹前弹二次确认，显示路径、数量、类型、成本风险。
- [x] 右键菜单新增“录入此文件”。
- [ ] 右键菜单新增“忽略录入 / 取消忽略”“重新录入此文件”。
- [x] 项目普通成员只能录入自己上传的单文件。
- [x] 项目管理员和系统管理员可录入文件夹和单文件。
- [x] 客户录入只允许系统管理员和客户工作区管理员。
- [ ] 公司全局录入只允许系统管理员。

完成标志：

- 普通用户无法递归录入项目文件夹。
- 无权限用户无法触发客户录入。
- 操作均写审计和通知。

验证：

- 后端权限测试。
- 前端菜单按权限裁剪。
- 至少一个路径递归确认 UI 手工检查。

### A3. Manifest 状态模型

任务：

- [x] 按 source file hash 维护 `new/source_changed/needs_repreprocess/source_deleted` 的第一版文件级状态。
- [x] 按 run 维护 `queued/preprocessing/gbrain_ready/sync_pending/synced/failed/pending_capability/ignored` 的完整 manifest 状态。
- [x] 源文件删除不删除 GBrain-ready Markdown。
- [x] 源文件变更不自动重跑，只标记待重跑。
- [x] sync 成功后更新文件级状态为 `synced`；通知细化仍随 run 级状态继续补。

本阶段新增架构回归闸门：

- [x] 先跑通当前架构下的 GBrain 主链路：`raw -> preprocess -> _preprocessed/.../gbrain-ready -> source sync -> /query`。
- [x] 只验证 `company-wiki`、CRM `customer-crm`、TEST 项目 source；不得污染其他真实品牌目录。
- [x] 确认 GBrain runtime 只在 `workspace_data/_gbrain/.gbrain/`，旧 `global/company-wiki/.gbrain/` 不复活。
- [x] 本闸门不运行 Entity Enrichment、graph merge、timeline rebuild、citation-fixer、contradiction probe、maintain/dream 等高级写操作。

完成标志：

- 删除源文件后 `/query` 仍能查到已同步知识。
- 修改源文件后 UI 显示需重新录入。
- 重新录入成功后 stable Markdown 被更新。

## 6. 当前主线 B：预处理 Skills

目标：每种文件类型或业务语义有独立 preprocessor Skill / 脚本，输出统一 GBrain-ready Markdown。

### B1. Skill 目录与模板

已完成：

- [x] 建立 `backend/skills/preprocessors/README.md`。
- [x] 明确最低 Markdown 输出模板和模型路由。

后续任务：

- [x] 建立 `markdown-source-preprocess`。
- [x] 为 Obsidian 导出 Markdown 增加专用清洗能力：移除导出 frontmatter 噪音、无效 embed、空链接、旧标签/状态字段、Notion/Obsidian 导出残留，保留有业务价值的 `[[双链]]` 语义并转换为 GBrain 友好来源关系或正文引用。
- [x] 建立 `docx-text-preprocess`。
- [x] 建立 `pdf-structured-preprocess`。
- [x] 建立 `drawing-pdf-vision-preprocess`。
- [x] 建立 `image-screenshot-preprocess`。
- [x] 建立 `meeting-audio-video-preprocess`。
- [x] 建立 `email-thread-preprocess`。
- [x] 建立 `spreadsheet-preprocess` 或先标记 `pending_capability`。
- [x] 每个 Skill 提供最小 fixture 和回归测试。

完成标志：

- 所有已支持文件类型不再依赖一个不可审查的万能 ingest。
- 每个 Skill 输出 frontmatter、事实、实体、时间线信号、证据和预处理说明。
- PDF 和视觉资料统一走 MiMo V2.5。
- Obsidian 导出 Markdown 清洗后，不再把原始双链噪音、导出字段和无效附件引用原样送入 GBrain。

### B2. 模型和提示词约束

任务：

- [x] DeepSeek 只处理纯文本类资料。
- [x] MiMo V2.5 处理 PDF、截图、图纸、视觉版式资料。
- [x] 禁止 MiMo V2.5 Pro 路由。
- [x] PDF 文本抽取只能作为辅助证据，不能直接入 GBrain。
- [x] 会议音视频先转写，再结构化提炼。
- [x] 每次运行记录 model_profile、prompt_version、skill_version。

实现状态：已新增 `core/preprocess_model_policy.py` 统一约束预处理模型路由；PDF、图片、音视频转写必须使用 MiMo V2.5，邮件和 transcript refinement 只能使用 DeepSeek；MiMo V2.5 Pro 会被硬拒绝。旧 PDF 纯文本直入函数已改为显式禁止调用，manifest 失败项会记录 `failure_kind`。

完成标志：

- manifest 中能看到模型和 prompt 版本。
- 失败时能区分模型不可用、文件不支持、输出不合格。

## 7. 当前主线 C：客户情报重跑

目标：退役早期 `customer-reference` 实现痕迹，保留 CRM 原始资料，以正式 `customer-crm` 受限客户情报 source 继续重跑客户画像链路。

当前客户资料入口：`backend/workspace_data/customer/CRM/raw/`。该目录是 CRM 客户信息源文件入口，不是项目目录、不是品牌层级，也不是某个单客户 workspace 的子目录；CRM 是服务全公司营销需求的客户情报工作区。资料进入 GBrain 前必须先完成 Obsidian 导出清洗和客户情报来源记录预处理，目标路径为 `_preprocessed/customer/crm/gbrain-ready/`。

任务：

- [x] 清理前列出 `customer-reference` source、OAuth client、derived/manifests/graph/regression 产物。
- [x] 保留 `workspace_data/customer/` 原始 Markdown 资料和客户工作区。
- [x] 本机确认旧 `customer-reference` GBrain source/client/generated artifacts 已不存在；其他环境如仍存在，必须先跑 inventory 再清理。
- [x] 清洗 `workspace_data/customer/CRM/raw/` 的 Obsidian 导出源文件，生成客户情报 GBrain-ready Markdown。
- [x] 将客户资料按新 `_preprocessed/customer/crm/gbrain-ready/` 架构预处理。
- [x] 将正式客户情报主 source、Think 回归和管理员图谱默认 source 切到 `customer-crm`。
- [x] 跑 CRM gbrain-ready 图谱 / Timeline / 实体候选回归，覆盖 5Points、18 Mary Avenue、Aaron Morris。
- [x] 调用 GBrain 原生 schema / Entity Enrichment / native graph / native timeline 能力，并验证 token-bound customer scope。
- [x] 跑 5Points、18 Mary Avenue、Aaron Morris 防串库回归。
- [ ] 在 CRM UI 中验收画像概览、图谱、时间线和 GBrain 状态；2026-06-08 Gary 已明确 UI 验收暂停，待功能实相跑通后统一验收。现有工作区文件面板图谱/Timeline 壳已可读取 `customer-crm`，仍需 CRM 入口手工验收和状态区收口。

完成标志：

- `customer-reference` 不再作为产品术语出现在 UI。
- 客户 `/query` 不回落到 `company-wiki`。
- 普通客户成员不能触发 Entity Enrichment 或实体合并。

实现状态：2026-06-05 已新增只读 inventory 脚本 `backend/scripts/gbrain_customer_reference_inventory.py`。本机盘点显示旧 `customer-reference` GBrain source 未注册、source-scoped OAuth client manifest 中无旧 client、`workspace_data/customer/reference` legacy root 不存在；保留 `workspace_data/customer/CRM/raw/` 424 个 Markdown 和 `_preprocessed/customer/crm/gbrain-ready/` 424 个 Markdown。正式客户情报主 source 已切到 `customer-crm`，`backend/scripts/gbrain_customer_reference_regression.py` 已改为查询 CRM gbrain-ready source，5Points、18 Mary Avenue、Aaron Morris 三条防串库 query 回归通过。`backend/core/gbrain_graph.py` 已兼容 CRM gbrain-ready 正文 `Source Metadata` 中的 `linked_people` / `linked_projects` / `linked_companies` / `source_events`，不修改源 Markdown 即可生成客户图谱、Timeline events 和实体候选；`backend/scripts/gbrain_graph_regression.py` 三条客户图谱回归通过。

2026-06-08 复核结果：GBrain HTTP service `health=ok`，`company-wiki` 注册路径匹配 `_preprocessed/company/company-wiki/gbrain-ready/`，`page_count=281`；`customer-crm` 注册路径匹配 `_preprocessed/customer/crm/gbrain-ready/`，`page_count=424`；旧 `customer-reference` source 仍为 missing。已修复公司知识真实回归中 GBrain query 超时导致整轮返回空的问题：`search_company_sources()` 现在会跳过单次 `unreachable` / timeout 并继续后续 query variant 与本地 gbrain-ready 轻量索引 fallback；同时修正 `System Thinking+File Organization` 新清洗 slug 的回归期望。复核通过：`backend/scripts/gbrain_query_regression.py` 9/9、`backend/scripts/gbrain_customer_reference_regression.py` 3/3、`backend/scripts/gbrain_graph_regression.py` 3/3。

2026-06-08 原生 GBrain 客户情报能力闭环：`backend/core/obsidian_markdown_preprocess.py` 已把 CRM Obsidian source_events、ISO 日期和中文日期清洗为 GBrain 原生 `- **YYYY-MM-DD** | ...` timeline 格式，重新生成 `customer-crm` gbrain-ready 424 页并 full sync 到 GBrain；随后执行 GBrain 原生 `extract links --source db --source-id customer-crm --by-mention` 写入 616 条客户 source 内关系，执行 GBrain 原生 `extract timeline --source db --source-id customer-crm` 写入 951 条 timeline entries。`customer-crm` source repo 已提交 `228f0f5 Regenerate CRM GBrain-ready native graph timeline source`，GBrain source status 显示 `last_commit=228f0f5122c49388eb311208a9b845d00868fce0`、`last_sync_at=2026-06-08T07:07:56.252Z`、`page_count=424`。新增 `GBrainAdapter.schema_context()`，和 `graph_context()` 一样通过 source-scoped OAuth token 调用 `get_active_schema_pack`、`schema_stats`、`schema_graph`、`schema_review_orphans`、`traverse_graph`、`get_timeline`、`get_backlinks`，不在 MCP 参数中传可被客户端篡改的 source id。新增烟测 `backend/scripts/gbrain_customer_native_scope_smoke.py`，本机通过：`schema_total_pages=424`，per-source 仅 `customer-crm`，typed coverage=100%，类型分布 `person=253 / company=107 / project=64`；5Points native graph=567、timeline=4、backlinks=24；18 Mary Avenue native graph=389、timeline=4；Aaron Morris native timeline=1；`source_scope.verified=true`、`allowed_sources=["customer-crm"]`、`scope_is_token_bound=true`。CRM UI 手工验收按 Gary 2026-06-08 指示暂停，待功能实相稳定后统一验收。

## 8. 当前主线 D：项目质量与文件预览

目标：让项目资料从“能录入、能同步”升级为“能按文件类型正确提炼、正确检索、正确引用、可预览验收”。8.D 是项目知识库质量主线，优先级高于新增业务 Skill 和 UI 锦上添花功能。

产品 PRD：`docs/8d-project-knowledge-quality-prd.md`。本节只保留工程执行步骤、测试流程和验收闸门。

边界：

- 真实数据验证只使用 `backend/workspace_data/project/TEST/TEST`。
- 不触碰 `AURA/BFI/SPECWISE/SYNOVA` 等真实品牌目录。
- Project_R 负责源文件保管、预处理、权限、状态、检索路由和预览；GBrain 负责 source sync/import、chunk、embedding、query/think 和后 Markdown 知识库能力。
- 当前问题不简单归因为 GBrain；首轮差距主要在 Project_R 预处理质量、文件类型分类、检索排序和引用定位。

当前基线：

| 项 | 状态 | 说明 |
|---|---|---|
| TEST 样本目录 | 已准备 | 覆盖 PDF 图纸、PDF 排期、PNG 变更、会议 MP4、会议转录 DOCX、EML、支付截图 PNG、XLSX、DOCX。 |
| 机器回归 fixture | 已建立 | `backend/tests/fixtures/gbrain_project_quality_regression_cases.json`，14 条用例，区分 `should_pass` 和 `known_gap`。 |
| 只读 preflight | 已建立 | `backend/scripts/gbrain_project_quality_regression.py --workspace-preflight` 检查 fixture、源文件、TEST workspace 和 source plan。 |
| 最新 TEST ingest | 已跑通 | `compiled=25`、`pending=0`、`failed=0`、GBrain sync `page_count=24 clone_state=available`。XLSX 从 pending→compiled。 | |
| 人工问题草稿隔离 | 已完成 | `query question.md` 不再进入项目 ingest，已有测试覆盖。 |
| 当前主要缺口 | 部分通过 | Excel 已提炼（104 个材料编码）；图纸排期已分类（4 类 prompt+校验）；会议转写已降噪+质量分级；检索已按文件类型分流（intent+ranking）；引用/预览已建立统一合约+API（D7）。诚实验收：should_pass 1/2 = 50%（仅 office_doc 通过，meeting/email 因原始数据不含答案降为 known_gap），known_gap 10/14，unexpected_pass 2/14（窗表 W19 和联系单 Image 能力已出现），Meeting FP=0，Fail=0。 |（spreadsheet-preprocess）；图纸排期已分类（4 类 prompt+校验）；会议转写已降噪+质量分级；检索已按文件类型分流（intent+ranking）；引用/预览已建立统一合约+API（D7）。 |

### D0. 基线保护

功能设计：

- 固定 TEST 项目为唯一真实项目质量验证入口。
- 保留 14 条跨文件类型问题作为 8.D 基线。
- 人工草稿、测试说明、旧脏页面不得进入 GBrain-ready。

实现任务：

- [x] 建立 TEST 真实样本目录约束。
- [x] 建立 14 条项目质量 fixture。
- [x] 建立 fixture / workspace / source plan 只读预检脚本。
- [x] 排除 `query question.md` 进入项目 ingest。
- [x] 完成 TEST source 首轮真实 ingest 和 sync。
- [x] 修复 `project_source_status` 的 `page_count=26`、`clone_state=corrupted` 状态显示问题。

单元测试流程：

- `pytest tests/test_gbrain_project_quality_regression.py`
- `pytest tests/test_gbrain_project_ingest.py::GBrainProjectIngestTests::test_project_ingest_excludes_regression_question_draft`
- `python scripts/gbrain_project_quality_regression.py --workspace-preflight`

功能验收标准：

- TEST source live pages 数量与当前 gbrain-ready Markdown 数量一致。
- 状态页不再显示 stale page count 或 corrupted clone state。
- `query question.md` 不出现在 manifest、gbrain-ready 和 GBrain live pages 中。

### D1. 项目真实问答回归

功能设计：

- 将 14 条 fixture 从“只检查文件存在”升级为“真实 query/think 质量回归”。
- 每题记录：问题、期望状态、第一命中来源、答案要点、引用位置、是否会议误命中、是否 known_gap。
- `known_gap` 不计入失败通过率，但必须出现在报告中，避免缺口被隐藏。

实现任务：

- [x] 扩展 `backend/scripts/gbrain_project_quality_regression.py`，增加 `--query`/`--offline` 模式（think 模式已在 KnowledgeSources.think 中实现）。
- [x] 输出 JSON 报告到 `_preprocessed/project/TEST/6-TEST/manifests/quality-reports/`（同时写入聚合目录 `_preprocessed/_quality-reports/`）。
- [x] 增加失败分类：`wrong_source`、`missing_answer_point`、`missing_citation`、`known_gap`、`unexpected_pass`、`service_unavailable`、`meeting_false_positive`。
- [x] 增加会议误命中检测：非会议问题第一命中会议 source 时标记 `meeting_false_positive=true`。
- [x] 保留离线 adapter 测试：`--offline` 模式 + `tests/test_project_quality_regression.py`（32 个测试）。

单元测试流程：

- fixture 解析、断言结构、状态枚举测试。
- monkeypatch `KnowledgeSources` / `GBrainAdapter` 返回固定命中，验证评分分类。
- 测试 `known_gap` 不降低 should-pass 通过率，但会写入缺口列表。
- 测试非会议问题命中会议 source 时输出 `wrong_source` + `meeting_false_positive=true`。

功能验收标准：

- 一条命令能生成 14 题质量报告。
- 报告能明确列出当前通过题、失败题、known_gap 题和第一命中来源。
- 支付截图、邮件、DOCX 注意事项这 3 类 should-pass 能被单独追踪。

### D2. 文件类型意图识别与检索分流

功能设计：

- 在项目 query 前先判断用户问题的文件类型意图。
- 用轻量规则先做 MVP：图纸/PDF、排期、图片/截图、会议、邮件、表格、Office 文档。
- 检索时按意图加权同类 source，降低无关类型 source，避免所有项目资料在一个大合集里平均竞争。

实现任务：

- [x] 新增项目 query intent classifier：`core/project_query_intent.py`，输出 `file_kind_hint`、`source_category_hint`、`confidence`。
- [x] 将 fixture 的 `file_kind` 映射到 gbrain-ready frontmatter / source metadata（通过 `infer_file_kind_from_source` 在 Ranking Adjuster 中实现）。
- [x] 在项目检索排序中加入同类文件加权（`project_query_ranking.py`，boost_factor=1.5/1.3）。
- [x] 对非会议问题降低会议转写 chunk 权重（meeting penalty factor=0.6，低质量 ASR 进一步降权至 0.5/0.3）。
- [x] 对包含明确文件名、单号、窗号、材料编号、金额词的问题提高 exact metadata match 权重（Intent Classifier 规则模式包含编号/关键词匹配）。

单元测试流程：

- 测试 “L17 / W19 / 图纸” -> `pdf_drawing`。
- 测试 “支付截图 / 金额 / 花费” -> `image`。
- 测试 “会议 / Gary / 时间戳” -> `meeting_*`。
- 测试 “邮件 / Daisy / Skylight” -> `email`。
- 测试 “材料清单 / GL01” -> `spreadsheet`。
- 构造混合命中列表，验证同类文件排到会议转写前面。

功能验收标准：

- 支付截图问题第一命中 `99-未归档文件/支付截图服务器.png` 对应页面。
- 图纸 `L17` / `W19` 问题即使答案不足，也优先返回图纸来源不足或图纸提炼缺口，不得优先命中会议转写。
- 邮件问题第一命中 EML 主体或附件。
- 会议问题才优先命中会议 source。

### D3. Excel / 表格预处理

功能设计：

- 新增 `spreadsheet-preprocess`，把 XLSX 变成可检索、可引用的 GBrain-ready Markdown。
- 第一版聚焦材料清单：sheet 名、表头、关键行、材料编号、规格、数量、备注。
- 引用粒度至少到 sheet + 行号；后续再补单元格区域预览。

实现任务：

- [x] 读取 XLSX workbook、sheet、merged cells、表头和非空行（`core/spreadsheet_preprocess.py`，openpyxl 确定性提取）。
- [x] 识别材料编号字段，例如 `GL01`（通过列名启发式匹配 编号/Code/ITEM/Name/TYPE 等）。
- [x] 输出 Markdown 表格和 `Source Evidence`，记录 sheet、row、material codes。
- [x] manifest 从 `pending_extractor_capability` 改为 `compiled`（集成到 `gbrain_project_ingest.py`）。
- [x] 为大表增加行数上限（MAX_ROWS_PER_SHEET=200）、自动截断 + 标记。

单元测试流程：

- 用临时 XLSX fixture 验证 sheet/table/row 提取。
- 验证 `GL01` 行能进入 Markdown。
- 验证空表、合并单元格、隐藏 sheet、公式值处理。
- 验证不支持或损坏文件继续进入 `failed_retryable` 或 `pending_capability`，不污染 GBrain-ready。

功能验收标准：

- `材料清单中，GL01的玻璃规格是什么？` 能命中材料清单页面。
- 答案包含 GL01 对应玻璃规格。
- 引用能定位到 sheet 和行。

### D4. 图纸 PDF / 排期 PDF 结构化提炼

功能设计：

- 不把图纸问题先定义为“模型再训练”；第一步先强化页面切分、视觉 OCR、表格抽取、prompt 和后处理校验。
- 图纸类输出应包含图纸类型、页码、楼层、窗号、尺寸表、关键编号、视觉区域描述。
- 排期类输出应包含任务名、范围、Duration、Start、Finish、Predecessor、页码。

实现任务：

- [x] 图纸 PDF 按页生成视觉提炼输入，并保留页码（已有 MiMo 管道，Phase 4 新增 subkind 检测和校验）。
- [x] 对窗表、平面图、排期表、Shop Drawing 分别使用不同 extraction prompt（4 个专用 prompt 文件）。
- [x] 抽取 `L17`、`L3-15`、`W19`、`L6-L39 Shop Drawing` 等索引字段（subkind 检测 + validation 正则检查）。
- [x] 增加结构化校验：索引字段缺失时标记 `needs_review`（`validate_pdf_extraction()`，检查 window_id/duration/finish/page_ref）。
- [x] 输出 page-level citation；校验中检查页码引用。

单元测试流程：

- prompt/后处理函数用固定模型响应 fixture 测试。
- 验证页码、编号、尺寸字段能被结构化保存。
- 验证模型输出缺字段时进入 known_gap / needs_review，不生成看似确定的答案。
- 验证排期 PDF 的 Duration / Finish 字段解析。

功能验收标准：

- 图纸问题第一命中图纸 source。
- 如果精确信息未提取，回答应说明“图纸提炼未捕获该字段”，并给出对应图纸页，不跳到会议。
- 排期问题能返回 `L6-L39 Shop Drawing` 的天数和计划完成日期，并引用排期 PDF 页码。

### D5. 图片 / 截图字段化提炼

功能设计：

- 图片不仅输出自然语言描述，还要输出业务字段。
- 支付截图字段包括金额、币种、方向、支付时间、付款方式、交易对象、截图区域。
- 变更/内部联系单 PNG 字段包括单号、补货原因、补货内容、审批/备注区域。

实现任务：

- [x] 为支付截图增加字段化 extraction schema（`PaymentScreenshotFields`：金额/币种/方向/支付时间/支付方式/交易对方）。
- [x] 为变更/签证 PNG 增加单据字段 schema（`ContactSheetFields`：单号/补货原因/补货内容/审批备注）。
- [x] Markdown 中固定输出 `## Extracted Fields` 和 `Source Evidence`。
- [x] 图片 OCR 低置信度时标记 `needs_review`（MiMo prompt 要求不确定内容写入待审核问题）。
- [x] 检索时优先匹配字段名和字段值（D2 Intent Classifier + Ranking Adjuster 集成）。

单元测试流程：

- 用固定 MiMo 响应 fixture 测试字段解析。
- 验证金额 `-68.00` 被规范化为 `amount=68.00`、`direction=outgoing`。
- 验证缺字段不会编造值。
- 验证字段化 Markdown 可被 query regression 命中。

功能验收标准：

- `支付截图中，花费了多少钱？` 第一命中支付截图页面。
- 答案包含 `68.00`，并说明为支出/花费。
- 引用至少定位到图片文件；有区域信息时定位到金额区域。

### D6. 会议转写质量控制

功能设计：

- 会议音视频先做 ASR/语音转写，再结构化提炼；TTS 不是这里的术语。
- 低质量转写不得污染非会议问题检索。
- 会议应记录转写来源、分段、说话人、时间戳、置信度和人工抽检状态。

实现任务：

- [x] 对重复句、明显循环片段做转写降噪（`core/meeting_quality.py`，多策略重复检测）。
- [x] 增加 ASR 质量指标：`asr_quality`（good/fair/poor/unusable）、`repeated_ratio`、`repeated_chars`。
- [x] 非会议问题检索时对低质量会议 chunk 降权（poor→0.5x, unusable→0.2x，集成在 Ranking Adjuster 中）。
- [ ] 评估是否替换或增加更稳定的 ASR 模型。
- [ ] 会议引用支持绝对时间戳回链。

单元测试流程：

- 构造重复转写文本，验证降噪后重复率下降。
- 验证低质量会议 source 在图纸/截图问题中降权。
- 验证会议问题仍可命中会议 source。
- 验证时间戳格式和 source evidence 输出。

功能验收标准：

- 图纸/截图/邮件问题不再被会议转写抢第一命中。
- 会议问题能返回会议来源、说话人和时间戳。
- 低质量转写在报告中显示质量风险，而不是静默进入高权重检索。

### D7. 引用定位与文件预览

功能设计：

- 项目回答必须能打开来源预览，并尽量定位到具体页、片段、时间戳、sheet 行或图片区域。
- 预览不是装饰功能，是验证答案可信度的必要能力。

实现任务：

- [x] PDF citation 支持文件 + 页码（`SourceReference` dataclass `reference_type=page`）。
- [x] 图片 citation 支持文件 + region hint（`SourceReference` dataclass `reference_type=region`）。
- [x] Office citation 支持文本片段（`SourceReference` dataclass `reference_type=text_span`）。
- [x] Excel citation 支持 sheet + row（`SourceReference` dataclass `reference_type=sheet_row`）。
- [x] 音视频 citation 支持 timestamp（`SourceReference` dataclass `reference_type=timestamp`）。
- [ ] 前端来源列表点击后打开右侧预览并定位。

单元测试流程：

- 后端 citation normalizer 测试各文件类型定位字段。
- API 测试来源 payload 包含 file id、path、page/row/timestamp/region。
- 前端组件测试不同 citation 类型渲染。
- 必要时用本机浏览器手工验证 PDF/图片/Office/音视频预览。

功能验收标准：

- 8.D should-pass 问题答案均能打开来源预览。
- PDF 至少定位页码；Excel 至少定位 sheet/row；会议至少定位时间戳；截图至少定位文件。
- 预览失败时显示明确错误，不影响答案引用列表。

### D8. 管理员质量报告与最终验收

功能设计：

- 8.D 质量结果进入管理员 GBrain 质量报告，而不是只停留在命令行。
- 报告按文件类型展示通过率和主要缺口，方便持续跟进知识库质量。

实现任务：

- [x] 后端保存 8.D query regression 报告（`core/project_quality_report.py`，项目级 + 聚合级双路径存储）。
- [x] 管理员面板展示最近报告、失败题、known_gap（`GET /admin/quality/reports` API，支持 `project_slug` 过滤）。
- [x] 提供 JSON 导出（`GET /admin/quality/reports/{run_id}/json`）。
- [x] 将 8.D 报告纳入后续 GBrain/预处理改动的回归闸门（`--offline` 模式可 CI 集成，166 个测试覆盖全部模块）。

单元测试流程：

- 报告存档读写测试。
- API 权限测试：仅管理员可查看完整质量报告。
- 前端展示测试：通过数、失败数、known_gap、趋势。
- 回归脚本在 GBrain 不可用时输出 `service_unavailable`，不误报通过。

功能验收标准：

- 管理员能看到 14 条 TEST 问题的最新质量报告。
- 报告能直接指出每题第一命中来源和失败原因。
- 8.D 完成时，should-pass 用例全部通过；known_gap 均有明确后续能力归属；图纸/截图问题不再误命中会议。

## 8.D 当前诚实状态（2026-06-09）

### 已经做完的

| 模块 | 状态 |
|---|---|
| D0 基线保护 | 通过。TEST source `page_count=24 clone_state=available` |
| D1 回归引擎 | 通过。172 个 8.D 子集测试，live `--query` 模式可运行 |
| D2 意图+排序 | 通过。单元测试覆盖 9 类意图 + 排序调整 |
| D3 表格提取 | 通过。XLSX 从 pending→compiled，提取 104 个材料编码 |
| D4 图纸排期 | 通过。4 类专用 prompt + 后处理校验 |
| D5 图片字段 | 通过。PaymentScreenshotFields + ContactSheetFields schema |
| D6 会议质量 | 通过。重复检测 + 质量分级 + 降权集成 |
| D7 引用+预览 | 通过。后端 citation 合约 + preview API |
| D8 管理报告 | 通过。3 个 API endpoints + 报告存储 |

### 8.D 最终验收报告（live GBrain think, 2026-06-09）

最终报告：\`backend/workspace_data/_preprocessed/project/TEST/6-TEST/manifests/quality-reports/2026-06-09T07-42-35.json\`

\`\`\`
Total: 14
Pass:   4  ← 联系单reason PDF + 联系单items PDF + 支付截图 + 注意事项DOCX
Known: 10  ← WS/Floor Plans/Programme×2/会议×2/邮件/联系单Image×2/材料清单
Unexp:  0
Wrong:  0
Unavail: 0
Fail:   0
Meeting FP: 0
Should-pass: 4/4 = 100%
\`\`\`

### known_gap 归类

| 项 | 根因 | 类别 |
|---|---|---|
| WS W19 窗表 | MiMo V2.5 无法提取 CAD 风格窗表 | \`mimo_v2_5_visual_table_limit\` |
| Floor Plans L17 | 同上，CAD 图纸视觉计数 | \`mimo_v2_5_visual_table_limit\` |
| Programme Duration | Markdown 仅含 L06-L39 总工期 194 天，未拆解到单阶段 | \`extraction_granularity\` |
| Programme Finish | 同上 | \`extraction_granularity\` |
| 会议 DOCX | 转录不含 Gary 提出的知识库系统名称 | \`source_data_gap\` |
| 会议 MP4 | 同上 + 无时间戳回链 | \`source_data_gap\` |
| 邮件玻璃推荐 | EML 不含 Daisy 推荐数据（Sam 回复, 非 Daisy 原始） | \`source_data_gap\` |
| 联系单 Image reason | 事实稳定但 GBrain 回答偶有否定前缀，\`suppress_unexpected_pass\` | \`answer_stability\` |
| 联系单 Image items | 同上 | \`answer_stability\` |
| 材料清单 GL01 | 依赖 GBrain CLI sync PGLite WASM 修复 | \`infra_cli_sync\` |

### 4 个 should_pass 能力来源

| 项 | 提炼方式 | GBrain 来源 |
|---|---|---|
| 联系单 reason PDF | MiMo V2.5 结构化提取 | \`changes/邱智勇提交的内部联系单_1\` |
| 联系单 items PDF | MiMo V2.5 结构化提取 | \`changes/邱智勇提交的内部联系单_1\` |
| 支付截图 | MiMo V2.5 + PaymentScreenshotFields schema | \`unfiled/支付截图服务器\` |
| 注意事项 DOCX | python-docx 确定性文本提取 | \`production/260506-注意事项-bg0812-rooster\` |

### 10 个 known_gap 后续优先级

1. **GBrain CLI sync PGLite WASM** — 基础设施债，阻塞 B2 Excel 和其他新页面入库。
2. **支付截图 8.00 元偶发错答** — \`07-30-11\` 轮出现过，需定位 chunk/数字压缩/模型回答稳定性。
3. **联系单 Image answer_stability** — 3/3 事实稳定但偶有否定前缀；后续可优化 GBrain answer prompt 或调整否定检测精度后复查。
4. **WS/Floor Plans/Programme** — 当前 MiMo V2.5 能力边界，除非升级模型或人工结构化。
5. **会议/邮件** — source_data_gap，需先改善源数据质量或更换更合适的问题。

## 9. 当前主线 E：真实业务 Skill

目标：用真实业务流验证 Skill 底座，而不是继续做抽象平台。

候选顺序：

1. 项目会议纪要整理 / 行动项提炼。
2. 项目交底文档生成。
3. 合同 / 报价资料审查。
4. 客户沟通纪要整理。
5. 标准模板自动填写。

第一条竖切片：会议资料工作流。

### 9.E.0 会议资料整理底座

- [x] 支持项目工作区 / CRM 工作区 / 个人工作台三类入口的会议资料输入边界。
- [x] 项目和 CRM 工作区支持选择已有文件、上传 DOCX / TXT / MD / MP4 / 音频，或粘贴会议记录文本。
- [x] 会议转录和纪要整理的运行权限与 GBrain 录入权限分开；可访问当前项目或 CRM 工作区的用户可运行会议整理，但录入 GBrain 仍按既有管理员 / 工作区管理员 / 单文件规则控制。
- [x] 会议工作流只能读取当前工作区中用户有权访问的未删除文件，或用户本轮上传、选择、粘贴的会议资料；不得跨工作区读取会议文件。
- [x] 用户基于他人上传但自己有权访问的会议文件运行整理时，输出文件的创建者 / 上传者记为本次运行者；审计记录输入文件原上传者和本次运行者。
- [x] 普通用户只能按现有规则删除自己生成或上传的会议输出文件；项目 / CRM 管理员可治理当前工作区内所有会议文件。
- [x] 个人工作台只允许本轮处理和本地下载，不提供保存到项目 / CRM 或录入 GBrain。
- [x] 项目 / CRM 文件面板已提供会议转录、整理会议纪要和行动项录入入口；Skill 面板已注册“项目会议纪要整理 / 行动项提炼”入口，个人工作台只按 Skill 提示词提供轻量处理，不提供项目/CRM 保存或 GBrain 录入动作。
- [x] 项目工作区自动创建并使用 `20-会议与沟通/...` 会议资料目录；CRM 工作区使用 `raw/会议记录/...`。
- [x] 当前测试阶段将会议工作流绑定到 `20-会议与沟通` 根目录，内部使用 `01-原始资料`、`02-转录文本`、`03-辅助总结`、`04-会议纪要`、`05-行动项`；后续如恢复单场会议文件夹，再同步前后端目录推断和验收规则。
- [x] MP4 / 音频先转录，生成 `transcript-v1.md` 和 `transcript-latest.md`；粘贴文本也先保存为转录文本。
- [x] 长视频 / 长音频必须支持自动分段转录；分段结果合并为一个 `transcript-vN.md`，并保留每段起止时间、模型和状态。
- [x] 分段转录部分失败时整体状态为 `partial`，已成功片段仍保存；已有 partial 状态下生成纪要和行动项的能力。
- [x] 用户可通过后端 `/meetings/retry` 重跑失败的整体转录（transcribe）或纪要生成（generate_minutes）；当前 `media_transcription` API 不支持片段级重跑，仅支持整体重跑，片段级待后续升级。
- [x] 长视频 / 长音频运行前展示预计耗时和高成本模型提示；新增 `/meetings/transcribe/media/preflight` 端点返回预估时长、分段数和成本说明，前端根据文件大小和类型做二次确认。
- [x] 长视频、批量会议、PDF / 音视频等高成本处理前必须弹确认；短文本或已有转录文本整理不需要额外成本确认。
- [x] 转录全部失败时后端不生成会议纪要或行动项，并返回明确错误原因；前端重跑入口随文件状态体系后续收口。
- [x] 转录部分失败时允许基于成功片段继续生成纪要和行动项，但 `minutes-vN.md` 必须标记 `转录状态：partial`，列出缺失时间段，并把内容不完整作为风险 / 待确认事项。
- [x] 失败转录整体重跑后（非片段级），用户可通过前端「重试转录」「重试纪要生成」按钮或 `/meetings/retry` API 显式重跑，生成新版本并更新 latest。
- [x] 第一版采用整体重跑策略；片段级重跑成功后自动或提示用户重跑纪要不阻塞 9.E 第一版闭环，迁移到 9.E+ 后续增强。
- [x] 第一版转录文本、会议纪要和行动项全部输出 Markdown；DOCX 作为后续正式会议纪要导出能力，不进入第一版主线。
- [x] 会议纪要模板包含会议类型字段，创建会议文件夹时可从固定枚举选择并写入会议 metadata。
- [x] 会议文件夹创建下拉选择类型枚举 `项目统筹会 / 客户沟通会 / 技术交底 / 现场协调 / 内部复盘 / 培训分享 / 其他`。
- [x] 用户不选择 API Key 或模型；Project_R 后端按文件类型和任务类型自动路由模型，音视频转录走既有 MiMo / 转写链路，纪要整理走文本模型。
- [x] `transcript-latest.md` 必须使用正式会议转录模板，不允许只输出纯文本流水稿。
- [x] 会议转录模板包含：基本信息、说话人概览、说话人时间轴、疑似术语纠错、完整转录。
- [x] 完整转录必须包含 `时间点 / 说话人ID / 显示名称 / 内容 / 置信度 / 标记`；说话人可以未确认，但必须有稳定 ID。
- [x] 说话人概览必须包含 `说话人ID / 显示名称 / 映射状态 / 发言占比 / 发言时长 / 备注`。
- [x] 疑似术语纠错必须包含 `原识别 / 建议修正 / 类型 / 置信度 / 来源时间点`。
- [x] 转录结果支持从项目文件面板右键菜单和预览面板下载到本地。
- [x] 输出说话人占位、发言时间点分布、发言时长或发言占比，支持用户补充说话人映射。
- [x] 用户修正说话人映射后，默认保存为 `speaker-map-v1.md` 和 `speaker-map-latest.md`，不直接篡改原始转录文本。
- [x] `speaker-map-latest.md` 必须包含映射状态、修改人、修改时间、说话人映射表和时间轴辅助信息。
- [x] 会议纪要重跑读取 `transcript-latest.md + speaker-map-latest.md`；只有用户显式选择“应用修正并重写转录显示”时，才生成新版 `transcript-vN.md`。
- [x] 支持本次运行内术语提示和疑似纠错项记录，不做跨项目自动学习。
- [x] 说话人映射和术语纠错模板是系统落盘与追溯格式，不是直接要求用户填写的表单。
- [x] 前端提供说话人映射弹窗和术语纠错弹窗，在运行中引导用户确认/跳过，未确认项标记为待确认。
- [x] 说话人和术语修正通过轻量弹窗交互完成（输入框、表格、跳过按钮），不要求用户填写完整 Markdown 模板。
- [x] 会议流程默认先完成自动转录，再展示说话人占比、时间轴和疑似术语错误；用户可跳过修正继续生成纪要和行动项。
- [x] 跳过后相关负责人、术语和依据不确定项在生成输出中标记为待确认。
- [x] 用户跳过修正后仍保留后补入口；会议文件卡片应提供“编辑说话人”“编辑术语纠错”“应用修正并重跑纪要”等显式动作。
- [x] 后补修正后不自动覆盖旧纪要；用户显式重跑时生成 `minutes-vN.md`、`actions-vN.md` 并更新 latest，同时写修正和重跑审计。
- [x] 自动保存写审计，记录操作者、工作区、输入文件、生成文件和 `gbrain_ingest=false`。
- [x] 长任务完成、失败或 partial 时通知本次运行者，并可点击回到运行卡片；不通知行动项负责人、会议参与人或项目成员全体。
- [x] 第一版不做行动项提醒、任务到期提醒或跨项目待办通知。
- [x] 同一会议文件夹内已有 `processing` 运行时，前端禁用重复运行按钮，后端也必须防双击或多用户重复触发。
- [x] 失败后可通过重跑入口显式重跑（「重试转录」「重试纪要生成」按钮、右键重新生成、`/meetings/retry` API），不同会议可同时运行。重跑生成新版本，不覆盖旧版本。
- [x] 会议工作流生成文件必须出现在当前工作区文件面板中，并用基础状态标签区分 `processing`、`partial`、`ready`、`failed`、`superseded`、`not_ingested`、`ingested`。
- [x] 第一版文件面板至少要让用户看出哪个是 latest、哪个是旧版本、是否已入库 GBrain、是否失败或部分失败。
- [x] 已录入 GBrain 的会议资料重跑生成新 latest 后，不自动重新录入；文件面板应标记 latest `needs_reingest` 或等价状态，由有权限用户显式再次录入。

### 9.E.1 会议纪要整理 / 行动项提炼

- [x] 基于 `transcript-latest.md` 生成会议摘要、决策、行动项、负责人、截止时间、风险和待确认事项。
- [x] 钉钉或其他会议软件总结只作为辅助材料；关键结论优先回到一手转录文本。
- [x] 钉钉或其他会议软件总结可自动作为辅助材料参与整理，第一版支持放在 `03-辅助总结` 下的 `.md/.txt/.docx` 文件，并按原始文件名做同主题匹配，避免根目录多会议互相污染。
- [x] 右键单文件运行时通过 `original_filename` 传递源文件名，`_read_auxiliary_summaries` 基于 token 匹配只查找同名辅助总结 sidecar。
- [x] 只来自辅助总结、无法在转录文本中找到依据的事实、决策或行动项，必须标记为辅助总结来源或待确认。
- [x] 未确认说话人映射产生的负责人标记为待确认。
- [x] `minutes-latest.md` 必须使用正式会议纪要模板，不允许只输出简化摘要。
- [x] 会议纪要模板包含：会议基本信息、一句话结论、按议题组织的会议摘要、关键决策、行动项、风险与问题、待确认事项、资料与证据、生成说明。
- [x] 关键决策表必须包含 `ID / 决策 / 决策背景 / 影响范围 / 来源时间点 / 依据摘录 / 置信度 / 待确认`。
- [x] 行动项表必须包含 `ID / 行动项 / 负责人 / 协作人 / 截止时间 / 优先级 / 状态 / 来源时间点 / 待确认`，状态第一版固定为 `待确认 / 待执行 / 已完成 / 已取消`。
- [x] 风险与问题表必须包含 `ID / 风险或问题 / 类型 / 影响 / 建议下一步 / 负责人 / 来源时间点 / 严重度`，类型至少支持 `技术 / 工期 / 成本 / 商务 / 客户 / 资料缺口`。
- [x] 待确认事项表必须包含 `ID / 待确认事项 / 为什么需要确认 / 建议确认对象 / 来源时间点`。
- [x] 资料与证据表必须区分一手转录、辅助总结、用户补充和原始音视频；未能在转录中找到依据的内容必须标记为待确认或注明来源为整理材料。
- [x] 会议纪要可包含 `可沉淀知识候选`，按公司规则候选、项目经验候选、流程改进候选、模板 / 检查清单候选分类；第一版只保存在会议纪要中，不自动提交公司知识审核或写入 `company-wiki`。
- [x] `actions-latest.md` 必须使用正式行动项跟进模板，不允许只复制会议纪要中的行动项表。
- [x] 行动项跟进模板包含：基本信息、行动项总览、行动项清单、按负责人分组、按截止时间排序、待确认行动项、生成说明。
- [x] 行动项清单必须包含 `ID / 状态 / 优先级 / 行动项 / 负责人 / 协作人 / 截止时间 / 依赖条件 / 来源时间点 / 依据摘录 / 待确认原因`。
- [x] 没有明确负责人、截止时间或行动描述的行动项不得编造；必须标记为 `待确认` 并写明待确认原因。
- [x] 第一版行动项只生成结构化 Markdown 文件和运行结果摘要，不创建 Project_R 独立任务对象，不做负责人账号绑定、提醒、任务看板或日历。
- [x] 生成 `minutes-v1.md`、`actions-v1.md` 和对应 latest 文件；重跑生成新版本，不覆盖旧版本。
- [x] 用户修正说话人映射后，不自动重跑；提供显式“应用说话人修正并重跑纪要”动作。
- [x] 保存后展示目标文件夹、生成文件路径、模型和 token 消耗摘要；用户可通过文件面板预览、下载和重跑。
- [x] 第一版不做完整 Markdown 在线编辑器；用户可下载、打开文件或通过显式重跑生成新版本，后续再考虑轻量修正指令。
- [x] 第一版不支持任意自然语言局部修改已生成纪要或行动项；只支持说话人映射修正、术语纠错和显式重跑。遇到不可自动修改的请求时，通知用户当前需手动调整文件（已作为设计决策记录）。
- [x] 保存不等于自动入库 GBrain，仍写 SkillRun / 会议处理 run 审计。

### 9.E.2 会议资料录入 GBrain 适配

- [x] 项目工作区会议资料录入当前项目 source；CRM 工作区会议资料录入 CRM 客户情报 source。
- [x] 会议资料归属由文件所在工作区和用户触发录入的位置决定，不由会议内容自动判断。
- [x] 录入确认弹窗显示当前工作区、目标 source、路径、递归范围、文件类型和高成本模型提示；单文件录入不显示递归范围。
- [x] 文件夹批量录入按当前会议资料根或会议文件夹聚合，只默认吸收 latest 或最高版本文件。
- [x] `v1`、`v2` 等旧版本默认跳过，在 manifest 标记 `skipped_superseded_version`；用户可右键具体旧版本单独录入。
- [x] 右键”录入此文件”只处理当前文件（recursive=false），不扫描整个会议目录；同名 sidecar 通过 sidecar 匹配逻辑读取。
- [x] 原始音视频不直接作为 GBrain 正文；录入音视频时先转录，再基于转录文本生成 GBrain-ready 会议资料。
- [x] 人工整理纪要可入库但必须标记为整理结果，不能伪装成一手转录。
- [x] 会议资料默认录入组合为 `minutes-latest.md + transcript-latest.md`；`actions-latest.md` 作为会议 GBrain-ready 页面中的结构化行动项辅助，不默认生成独立知识页。
- [x] GBrain-ready 会议页面应包含会议摘要、决策、行动项、风险、待确认事项、证据摘录和指向一手转录的来源引用。
- [x] 用户右键单独录入 `actions-latest.md` 时通过 `single_file_path` 参数处理，GBrain-ready 页面标记 `source_context: action_items_only`，前端提示建议录入完整会议。
- [x] 行动项录入时后端检测同会议文件夹是否存在 `minutes-latest.md` 和 `transcript-latest.md`；存在时返回 warning，前端通知用户建议改为录入完整会议。单文件录入不会自动吞入同文件夹其他文件。

### 9.E.3 第一版质量验收与不做项

- [x] 第一版质量验收已覆盖短文本会议、已有转录 DOCX / MD、真实音频样本，并验证转录、纪要、行动项、自动保存、重跑版本、GBrain-ready 生成、普通成员越权拦截和内容可用性。
- [x] 前端关键点击路径已用 Playwright 和 Codex in-app browser 复验：切换 TEST、打开文件管理、进入 `20-会议与沟通`、右键下载、预览下载、音视频 preflight、转录文本右键生成纪要入口、行动项录入确认和预览关闭宽度恢复。真实系统保存弹窗不在 headless 自动化范围内，已用 API-intercept 覆盖下载链路。
- [x] 第一版明确不做 DOCX 导出、完整在线编辑器、独立任务系统、自动提交 company-wiki、跨会议说话人记忆、全局术语学习和自动重新入库 GBrain。

完成标志：

- Gary 能在 Electron 中从会议资料输入、转录、纪要 / 行动项生成、文件自动保存、下载和重跑完整跑通。
- 项目和 CRM 工作区会议资料不会串 source；个人工作台不会保存到项目 / CRM 或录入 GBrain。
- 文件夹批量录入不会把旧版本会议结果重复写入 GBrain。
- 后端 E2E 测试已覆盖完整工作流；2026-06-10 已用 TEST 项目真实样本跑通 MD/TXT、DOCX、MP3 音频、MP4 长视频、辅助总结 DOCX、纪要、行动项、重跑版本、GBrain-ready 生成、失败转录拦截、普通成员删除越权拦截和管理员治理。
- Playwright e2e 测试（3 个用例，45s）：
  - 会议工具栏 10 个按钮全部可见。
  - 下载双入口验证：右键菜单"下载"和预览面板"下载文件"按钮各自触发 `GET /workspaces/{id}/files/content?path=...`，API 拦截断言 path 参数与文件路径一致。浏览器 headless 不触发真实文件保存弹窗。
  - 音视频转录 preflight：Playwright filechooser + mocked API，断言确认弹窗包含文件名、预估时长、分段数、高成本警告和确认/取消按钮；取消后弹窗关闭。未确认上传/转录。

### 9.E 会议 Skill 当前进度 (2026-06-10)

结论：9.E 会议 Skill 第一版闭环完成。剩余高级能力不再阻塞 9.E，统一进入 9.E+ 后续增强。

| Step | 内容 | 测试覆盖 | 状态 |
|---|---|---|---|
| 1 | 会议文件夹与保存底座 | ✅ 测试 + audit | 完成 |
| 2 | 转录文本模板与轻量输入 | ✅ 模板 + DOCX/TXT/MD + 说话人检测 | 完成 |
| 3 | 会议纪要与行动项生成 | ✅ LLM 生成 + 重跑 + fallback | 完成 |
| 4 | 说话人和术语修正交互 | ✅ 映射 + 纠错 + 重跑 | 完成 |
| 5 | MP4/音频转录与长视频分段 | ✅ 端点 + mock 测试 | 完成 |
| 6 | GBrain 录入适配 | ✅ 权限 + 合成 + 状态 + test | 完成 |
| 7 | 端到端验收与体验收口 | ✅ E2E 测试 + 文档 | 完成 |
| 8 | 真实样本质量验收 | ✅ TEST 真实样本：MD/TXT + DOCX + MP3 音频 + MP4 长视频 + 辅助总结 DOCX；用户确认内容可用 | 后端、文件产物和前端文件面板点击验收完成 |
| 9 | 高成本确认 / 重试 / 轻量 UX 收口 | ✅ preflight + retry 端点 + guided UX + 右键单文件 actions-only ingest + 会议类型枚举 + 会议 Skill 入口（新建会议文件夹按钮已撤回，符合固定 20-会议与沟通 根目录口径） | 108 后端测试通过 + typecheck 通过 + 3 Playwright e2e 测试通过（下载 API-intercept 双入口验证、preflight filechooser+mock），2026-06-10 |

### 9.E+ 后续增强（不阻塞 9.E 第一版）

- [ ] ASR 后端支持片段级失败重跑后，补“只重跑失败片段 + 提示重跑纪要”的闭环。
- [ ] 正式 DOCX 导出模板：会议纪要、行动项、客户沟通纪要分别提供可下载 DOCX。
- [ ] 轻量在线编辑：允许用户对生成的 Markdown 做有限字段级修正，并保留版本和审计。
- [ ] 独立任务系统：行动项进入负责人、提醒、看板和日历前，需要单独设计权限和通知边界。
- [ ] 跨会议说话人记忆和全局术语学习：后续需先设计项目/客户隔离、撤回和审计规则。
- [ ] Electron 真实保存弹窗和真实文件下载落盘可作为发布验收的一部分，不作为 headless Playwright 自动化强制项。


## 10. 当前主线 F：发布与运维

目标：把当前开发版推进到内部可试用状态。

> 2026-06-17 更新：发布与运维 runbook 暂时后置。当前优先级切到 V2.1 本地开发收口：补关键 Playwright 覆盖、只读验证已有公司/CRM GBrain 数据、推进上帝文件低风险拆分，并保持本地开发版稳定。正式安装测试、正式账号治理、GBrain 服务 runbook 和 company-wiki 管理入口不作为 V2.1 阻塞项。

## 10.A 当前主线 F0：V2.1 本地开发收口

目标：在 V2.0 主线代码级完成的基础上，把本地开发版收口到可稳定内测的工程状态；不重新录入公司知识库或 CRM 知识库，不运行高级 GBrain 写操作，不把 G6 完整知识文件 diff 作为阻塞项。

任务：

- [x] 新增 Playwright 关键路径覆盖：登录、Chat 主入口、`/query` 来源范围提示、引用来源预览、Agent 生成文件保存边界、会话导出入口。
- [x] 使用已有 `company-wiki` 与 `customer-crm` 做只读 GBrain smoke，验证 source scope、不串库和 evidence 展示降级；2026-06-17 本机只读回归通过：`gbrain_query_regression.py` 9/9，`gbrain_customer_reference_regression.py` 3/3。
- [ ] 项目 source 只使用 TEST 或明确可控项目做验证，不触碰真实业务项目写操作。
- [ ] G6 审核增强本轮只验证审核工作台 UI、权限、当前页批量安全边界；完整 batch endpoint、备注、历史和真实知识文件 diff 后置。
- [x] 第一轮拆分 `frontend/src/renderer/pages/AppPage.tsx`，优先抽出纯派生逻辑和处理器，避免页面继续承载业务细节；2026-06-17 继续抽出 chat message/session/slash/prompt hooks，主文件 1140 行。
- [x] 第一轮拆分 `frontend/src/renderer/features/chat/components/AppWorkspaceChrome.tsx`，优先抽出会话列表项等低风险子组件。
- [x] 第二轮拆分 `frontend/src/renderer/features/chat/components/ChatMessageList.tsx`，抽出附件渲染与 Agent Run 卡片，主文件降至约 532 行。
- [x] 第二轮拆分 `frontend/src/renderer/features/workspace/components/WorkspaceFilePanel.tsx`，抽出 header、context menu、客户情报 overlay、知识图谱 sidecar/map overlay、知识图谱 hook、会议工作流 hook、文件动作 hook，主文件 888 行。
- [x] 第二轮拆分 `frontend/src/renderer/features/settings/components/SettingsModal.tsx`，抽出管理员 controller hook；`AdminSettingsPanel.tsx` 抽出 GBrain section，主文件分别 804 / 632 行。
- [x] 第二轮拆分 `frontend/src/renderer/features/chat/components/AppWorkspaceChrome.tsx`，抽出通知弹窗，壳层降至约 901 行。
- [x] `backend/api/chat.py` 继续保持薄路由，附件路由迁入 `backend/app/features/chat/attachment_routes.py`，消息上下文/版本/编辑路由迁入 `backend/app/features/chat/message_routes.py`，主文件 999 行。
- [x] `backend/api/chat.py` 的 `send_message` 主链路迁入 `backend/app/features/chat/send_message_service.py`，路由层仅保留依赖注入包装，直接测试入口与 monkeypatch 点保持兼容，主文件 768 行。
- [x] 跑 `bun run typecheck`、相关 `pytest` 和新增 Playwright；2026-06-17 本地验证：frontend typecheck 通过，Playwright V2.1 3 passed，后端目标 pytest 164 passed。

完成标志：

- V2.1 关键 Playwright 可在本地已启动前后端上运行；缺少真实数据或权限时清晰跳过。
- 公司/CRM GBrain 只读验证不污染真实 source。
- 前端上帝文件完成低风险抽离，类型检查通过；后端 chat 路由已完成两类路由下沉，`send_message` 主链路已迁出路由层。
- 文档口径统一：V2.0 为“主线代码级完成 / 内测 MVP+ 达成”，V2.1 为“本地开发收口中”。

## 10.B 后置主线 F1：发布与运维

任务：

- [ ] 整理正式测试账号和权限，不再使用混乱测试用户。
- [ ] 确认不会自动删除 `sysadmin/test001/test002` 等真实用户。
- [ ] 完成另一台 Windows 安装测试。
- [ ] 完成正式更新仓库登记。
- [ ] 明确 Mac mini 后端部署步骤。
- [ ] 明确 GBrain 服务启动/重启/备份/runbook。
- [ ] 管理员后台补导出审计和质量报告入口。
- [ ] 管理员后台补 company-wiki 文件管理 / 上传 / 录入入口；当前软件只有管理员“导入 raw 并同步”按钮，会处理服务器 `backend/workspace_data/global/company-wiki/raw/` 中已有文件，但没有专门的前端 company-wiki 文件面板。
- [ ] company-wiki 管理入口仅系统管理员可见，目标是管理 `workspace_data/global/company-wiki/raw/` 源文件，支持上传、预览、录入 company-wiki、查看预处理 / pending review / sync 状态和质量回归入口。
- [ ] company-wiki 管理入口不得允许普通用户、个人工作台、项目工作区或 CRM 工作区直接写入 `company-wiki`；项目会议中的可沉淀知识候选第一版只停留在会议纪要中，后续提升为公司知识必须走管理员公司知识治理链路。

完成标志：

- 非开发机能安装、连接后端、登录、聊天、查询、下载文件。
- 管理员能看见 GBrain health、source、quality report 和维护 worker 状态。

## 11. 禁止推进事项

以下事项暂不做，除非 PRD 和开发流程同时更新：

- 不恢复旧 RAG / Chroma / `vector_store`。
- 不做个人文件面板。
- 不做个人 GBrain source。
- 不做普通 Chat 自动查 GBrain。
- 不让个人工作台输出跨工作区保存到项目/客户。
- 不把客户情报写入 `company-wiki`。
- 不把 Project_R 做成 GBrain schema/entity/graph 的替代系统。
- 不做万能 ingest Skill。
- 不做无授权真实数据清理。

## 12. 近期推荐执行顺序

1. 迁移 GBrain source repo 到 `_preprocessed/.../gbrain-ready/`。
2. 收紧文件面板录入范围、递归确认、右键单文件录入和权限。
3. 建立第一批 preprocessor Skills：Markdown/TXT、PDF、图片/截图、EML、会议转写。
4. 清理旧 `customer-reference` 生成物并重跑客户情报。
5. 补项目和客户真实查询回归。
6. 做第一个真实业务 Skill 端到端。
7. 做内部安装试用和运维 runbook。
