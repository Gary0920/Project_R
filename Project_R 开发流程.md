# Project_R 开发流程

版本：v3.1  
更新时间：2026-06-05  
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
| 业务 Skill | 底座完成 | 显式启动、补参、运行卡片已有，需真实业务 Skill 验收。 |
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

目标：清理早期 `customer-reference` 生成物，保留原始资料，用 GBrain 原生客户情报能力重新跑客户画像链路。

当前客户资料入口：`backend/workspace_data/customer/CRM/raw/`。该目录是 CRM 客户信息源文件入口，不是项目目录、不是品牌层级，也不是某个单客户 workspace 的子目录；CRM 是服务全公司营销需求的客户情报工作区。资料进入 GBrain 前必须先完成 Obsidian 导出清洗和客户情报来源记录预处理，目标路径为 `_preprocessed/customer/crm/gbrain-ready/`。

任务：

- [ ] 清理前列出 `customer-reference` source、OAuth client、derived/manifests/graph/regression 产物。
- [ ] 保留 `workspace_data/customer/` 原始 Markdown 资料和客户工作区。
- [ ] 删除旧 GBrain source/client/generated artifacts。
- [x] 清洗 `workspace_data/customer/CRM/raw/` 的 Obsidian 导出源文件，生成客户情报 GBrain-ready Markdown。
- [x] 将客户资料按新 `_preprocessed/customer/crm/gbrain-ready/` 架构预处理。
- [ ] 调用 GBrain 原生 schema / Entity Enrichment / graph / timeline 能力。
- [ ] 跑 5Points、18 Mary Avenue、Aaron Morris 防串库回归。
- [ ] 在 CRM UI 中展示画像概览、图谱、时间线和 GBrain 状态。

完成标志：

- `customer-reference` 不再作为产品术语出现在 UI。
- 客户 `/query` 不回落到 `company-wiki`。
- 普通客户成员不能触发 Entity Enrichment 或实体合并。

## 8. 当前主线 D：项目质量与文件预览

目标：让项目录入和项目查询具备可验收质量，而不只是“能同步”。

项目真实目录测试约束：Gary 已提供 `backend/workspace_data/project/TEST/TEST` 作为项目测试路径。需要在真实 `workspace_data/project/` 下验证项目 source、文件录入、预处理、sync 或 query 时，只能使用该 TEST 路径；不得在 `AURA/BFI/SPECWISE/SYNOVA` 预创目录中放测试文件、生成 gbrain-ready 结果或触发 source sync。

任务：

- [ ] 补项目真实样本回归集。
- [ ] 补 PDF 页码 / 图纸页 / 图片区域级 citation。
- [ ] 补会议绝对时间戳回链。
- [ ] 补音视频转写置信度和人工抽检状态。
- [ ] 补批量邮件线程合并。
- [ ] 补 Office/PDF/图片/音视频文件预览 UI 质量。
- [ ] 补项目 `/query` Think 回归。

完成标志：

- 项目回答能打开来源预览，并定位到源文件、页码、片段或时间戳。
- 复杂资料失败不会污染 GBrain，只进入 `pending_capability` 或 `failed`。

## 9. 当前主线 E：真实业务 Skill

目标：用真实业务流验证 Skill 底座，而不是继续做抽象平台。

候选顺序：

1. 项目会议纪要整理 / 行动项提炼。
2. 项目交底文档生成。
3. 合同 / 报价资料审查。
4. 客户沟通纪要整理。
5. 标准模板自动填写。

任务：

- [ ] 选择一个真实业务 Skill 作为第一条端到端验收。
- [ ] 明确输入字段、文件引用、输出格式和保存位置。
- [ ] 输出先作为本轮结果展示。
- [ ] 项目/客户工作区内允许确认保存到当前工作区 `99-未归档文件`。
- [ ] 保存后写审计，不自动入库 GBrain。
- [ ] 补 SkillRun 状态、失败提示和重跑逻辑。

完成标志：

- Gary 能在 Electron 中从选择 Skill 到生成结果完整跑通。
- 输出能下载到本地或保存到当前工作区。
- Skill 不会越权读取其他工作区资料。

## 10. 当前主线 F：发布与运维

目标：把当前开发版推进到内部可试用状态。

任务：

- [ ] 整理正式测试账号和权限，不再使用混乱测试用户。
- [ ] 确认不会自动删除 `sysadmin/test001/test002` 等真实用户。
- [ ] 完成另一台 Windows 安装测试。
- [ ] 完成正式更新仓库登记。
- [ ] 明确 Mac mini 后端部署步骤。
- [ ] 明确 GBrain 服务启动/重启/备份/runbook。
- [ ] 管理员后台补导出审计和质量报告入口。

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
