# Project_R PRD

版本：v3.0  
更新时间：2026-06-04  
产品负责人：Gary

## 1. 产品定位

Project_R 是公司内部 AI 智能办公辅助系统。它不是通用聊天壳，也不是独立知识库系统，而是公司员工使用 AI、业务文件、项目资料、客户情报和 GBrain 知识能力的统一桌面入口。

核心定位：

- 普通 Chat：处理日常问答、改写、解释、头脑风暴和轻量办公任务。
- GBrain 知识问答：通过显式 `/query` 或知识库 Skill 查询可信公司/项目/客户知识。
- 工作区文件治理：项目和客户资料在受控工作区内上传、预览、引用、录入和审计。
- 业务 Skill / Agent：围绕公司真实业务流程生成文件、整理信息、填写模板、触发受控任务。
- 管理后台：用户、权限、GBrain、知识审核、审计、质量回归和系统交付的管理入口。

## 2. 用户与场景

目标用户：

| 用户 | 主要诉求 |
|---|---|
| 普通员工 | 聊天、查询公司知识、在项目中处理资料、调用业务 Skill。 |
| 项目成员 | 上传项目资料、引用文件、查询公司知识 + 当前项目资料。 |
| 项目管理员 | 管理项目成员、隐藏/开放项目、录入项目知识、管理文件。 |
| 客户工作区成员 | 查看授权客户资料、客户画像、图谱、时间线和客户知识问答。 |
| 客户工作区管理员 | 触发客户情报录入、Entity Enrichment、实体处理等受控 GBrain 写操作。 |
| 系统管理员 | 用户管理、全局知识录入、GBrain 状态/维护/回归、审计和发布。 |

典型场景：

- 员工在个人工作台进行普通 Chat，受内置提示词和用户自定义提示词影响。
- 员工用 `/query` 查询公司规则、流程、标准和培训资料。
- 项目成员在项目工作区上传会议、邮件、图纸、PDF、截图等资料。
- 项目工作区查询范围为 `company-wiki + 当前项目 source`。
- 客户工作区只查询受限客户情报数据，用于客户画像、People Graph、Company Graph、Project Graph。
- 管理员录入公司知识、运行 GBrain 回归、维护 citation-fixer、审核低分反馈和缺口/冲突项。

## 3. 产品边界

### 3.1 Project_R 做什么

- 提供 Electron 桌面工作台。
- 管理用户、会话、工作区、文件、权限、审计和通知。
- 保管公司、项目、客户原始源文件。
- 把源文件预处理为 GBrain 友好的 Markdown。
- 通过后端 adapter 转发 GBrain query/think/sync/maintain/graph/timeline/entity 操作。
- 展示 GBrain 返回的回答、引用、gap、conflict、warning、图谱和时间线。
- 承载公司业务 Skill / Agent 的显式入口和执行记录。

### 3.2 Project_R 不做什么

- 不自建替代 GBrain 的知识库内核。
- 不恢复旧 Wiki Router、Chroma、`vector_store` 或旧 RAG fallback。
- 不在普通 Chat 中自动查询 GBrain。
- 不让个人工作台成为个人文件库、个人知识库、个人记忆系统或 GBrain source。
- 不把用户源文件删除等同于删除 GBrain 知识。
- 不让普通用户触发客户 Entity Enrichment、实体合并、citation-fixer、contradiction probe 等写操作。

## 4. 系统架构

| 层 | 说明 |
|---|---|
| Electron 前端 | React + Vite + TypeScript，Proma 风格工作台外壳，所有业务能力走后端 API。 |
| FastAPI 后端 | 用户、会话、工作区、文件、Skill、GBrain adapter、审计、通知和管理员 API。 |
| SQLite | 本地运行数据库，保存用户、会话、工作区、文件、审核、审计等业务数据。 |
| LLM Provider | 后端统一 Provider 抽象，支持 DeepSeek、MiMo 等模型 profile 和多 Key 轮询。 |
| GBrain | 真正知识库内核，负责 source sync/import、chunk、embedding、query、think、citation、schema、Entity Enrichment、graph、timeline、maintain。 |
| Workspace Data | Project_R 后端资料根目录，保存原始源文件和预处理产物。 |

正式业务调用原则：

- Project_R 通过 GBrain HTTP/MCP 常驻服务和后端 service account adapter 调用 GBrain。
- CLI 只用于开发期初始化、诊断、人工运维和应急排障。
- 后续不得无记录地直接修改 `reference/gbrain-master`；必要改动必须记录到 `patches/gbrain/`。

## 5. 工作区模型

| 类型 | 文件面板 | GBrain 行为 | 查询范围 |
|---|---|---|---|
| 个人工作台 | 不提供右侧个人文件面板 | 不入库、不做 source 治理 | `/query` 只查 `company-wiki` |
| 项目工作区 | 项目资料文件面板 | 录入当前项目 source | `company-wiki + 当前项目 source` |
| 客户工作区 | 客户资料文件面板 | 录入受限客户情报 source，后续由 GBrain Entity Enrichment 精炼 | 仅客户情报数据 |
| 公司全局知识 | 管理员入口 | 录入 `company-wiki` | `company-wiki` |

项目默认开放给所有有效用户；隐藏项目仅系统管理员、项目成员白名单和授权组别可见。工作区管理员是 scoped admin，不等同于系统管理员。

客户工作区不是项目工作区的变体。`workspace_data/customer/` 用于客户邮件、会议、联系人、公司、项目关系、沟通事件和销售判断线索，服务 CRM 客户画像场景。

## 6. GBrain 与资料预处理

### 6.1 目录架构

用户源文件目录只保存原始资料，不再在源文件目录内创建 `derived/`。

目标预处理目录：

```text
backend/workspace_data/_preprocessed/
├── company/company-wiki/{gbrain-ready,runs,manifests}
├── project/{brand}/{workspace_id}-{project_slug}/{gbrain-ready,runs,manifests}
└── customer/{workspace_id}-{customer_slug}/{gbrain-ready,runs,manifests}
```

- `gbrain-ready/`：GBrain source repo。
- `runs/`：预处理过程文件，仅管理员或后端排障可查看。
- `manifests/`：源文件 hash、状态、模型、prompt、Skill、错误和 GBrain sync 状态。

旧 `workspace_data/.../derived/` 只视为 MVP 历史实现，后续应迁移到上述架构。

### 6.2 录入规则

- 文件面板点击“录入”默认处理当前打开路径，并递归包含子文件夹。
- 递归录入必须二次确认，显示路径、文件数量、类型、高成本模型/转写提示和权限范围。
- 文件右键菜单提供“录入此文件”“重新录入此文件”“忽略录入 / 取消忽略”。
- 源文件删除不删除 GBrain-ready Markdown，也不删除 GBrain 知识。
- 源文件变化后标记 `source_changed` / `needs_repreprocess`，不自动重跑。

权限：

| 范围 | 谁能录入 |
|---|---|
| 公司全局知识 | 系统管理员 |
| 项目文件夹递归录入 | 系统管理员、项目管理员 |
| 项目单文件录入 | 系统管理员、项目管理员、上传者本人 |
| 客户情报录入 | 系统管理员、客户工作区管理员 |

### 6.3 模型路由

| 文件类型 | 路由 |
|---|---|
| Markdown / txt / DOCX 等纯文本 | DeepSeek |
| PDF | MiMo V2.5，文本抽取只能作为辅助证据 |
| 截图 / 图纸 / 设计图 / 视觉版式资料 | MiMo V2.5 |
| 音频 / 视频会议 | 转写脚本，再用 DeepSeek 做结构化提炼 |
| 邮件 | 邮件线程预处理 + DeepSeek，附件递归分发到对应预处理 Skill |
| Excel / ZIP / 复杂附件 | 未支持前标记 `pending_capability` |

禁止使用 MiMo V2.5 Pro 作为当前预处理路线。

每类文件必须有独立 preprocessor Skill / 脚本，放在 `backend/skills/preprocessors/`，并遵守该目录 README 的输出模板。

## 7. Chat 与知识查询

普通 Chat 和 GBrain 相互独立。

- 普通 Chat 不自动查 GBrain。
- `/query` 是唯一面向用户的知识库问答指令或等价 Skill 入口。
- 个人工作台 `/query` 只查 `company-wiki`。
- 项目工作区 `/query` 查 `company-wiki + 当前项目 source`。
- 客户工作区 `/query` 只查客户情报数据，不回落到 `company-wiki`，不查项目 source。
- 普通用户不提供全量知识库浏览器，不展示 source 列表、文件目录、chunk、入库状态、质量报告或其他知识库元数据。
- 普通用户侧的知识库体验重点是来源透明：查询前显示本次会查询哪些范围、不会查询哪些范围；查询后只展示本轮回答实际引用到的片段、标题、必要路径、定位信息和 gap/conflict/warning 摘要。

GBrain 返回的 citation、gap、conflict、warning 由 Project_R 在聊天和右侧来源面板中展示；用户可提交 gap/conflict/warning 到知识审核。

## 8. 业务 Skill / Agent

业务 Skill 是 Project_R 的长期差异化能力，但必须显式触发。

当前原则：

- 用户通过 Skill 面板或明确选择启动 Skill。
- 普通自然语言不自动触发半成品 Skill。
- 个人工作台可运行轻量生成类 Skill，输出默认只作为本轮结果展示，可复制或下载到本地。
- 项目/客户工作区 Skill 输出先展示结果，用户确认后可保存到当前工作区 `99-未归档文件`。
- 保存到工作区不等于 GBrain 入库；保存后的文件按当前工作区规则进入待录入候选。

预处理 Skill 与业务 Skill 分开：

- 预处理 Skill：把源文件变成 GBrain-ready Markdown。
- 业务 Skill：填写模板、生成报告、整理业务输出、辅助流程执行。

## 9. 客户情报

客户情报是受限业务情报，不是公司公共知识库。

产品目标：

- 使用 `workspace_data/customer/` 中的客户资料，通过 Project_R 预处理后投喂 GBrain。
- 尽可能使用 GBrain 原生 schema pack、Entity Enrichment、graph、timeline、backlinks、think 等能力。
- 自动形成 People Graph、Company Graph、Project Graph，用于销售团队判断客户、公司、项目和关键人。

Project_R 客户情报 UI 是 GBrain 原生能力的展示和转发壳，不自建客户画像内核。

建议入口：

- 画像概览
- 图谱
- 时间线
- 实体处理
- GBrain 状态

`customer-reference` 只视为早期 MVP source id，不是产品术语。现有旧客户参考数据可清理生成物后，用 GBrain 原生客户能力重新跑。

## 10. 管理后台

管理员需要能管理：

- 用户：新增、禁用、角色、密码重置。
- 工作区：项目/客户工作区、隐藏/开放、成员和授权组别。
- GBrain：health、source、sync、doctor、jobs、quality regression。
- 知识审核：用户反馈、GBrain gaps/conflicts/warnings、显式提升公司知识。
- 维护任务：citation-fixer、contradiction probe、Dream Cycle、worker 诊断。
- 审计日志：用户、时间、操作、结果。
- 模板和 Skill 状态。
- 客户端更新包和版本检查。

所有真实用户、真实工作区、真实 source 的修改必须有明确授权和审计。

知识库元数据入口属于管理员能力：

- 系统管理员可查看公司全局知识、项目 source、客户 source 的状态、入库情况、失败原因、质量报告和审核入口。
- 项目管理员只可查看当前项目 source 相关状态。
- 客户工作区管理员只可查看当前客户 source 相关状态。
- 普通用户不能通过 UI 枚举知识库元数据，只能在显式查询后查看本轮引用来源。

## 11. 当前代码进度快照

已完成或已有 MVP：

- 登录、用户、会话、多轮 Chat、提示词系统。
- Proma 风格主工作台、侧栏、标签页、归档、搜索、通知中心。
- 项目/客户工作区文件面板、上传、删除、回收站、权限、审计、文件预览 MVP。
- GBrain 正式接入、`/query` native think、公司/项目/客户 source scope 初步闭环。
- 项目资料录入 MVP：PDF/图纸、图片/截图、MP4、会议转写、EML 和附件递归。
- 客户情报 MVP：客户工作区权限、早期 `customer-reference` source、防串库回归、图谱/时间线基础入口。
- 管理员后台 MVP：用户、审计、知识审核、GBrain 状态、维护、质量回归。
- 文件生成 tracer bullet：基础 `.docx` 生成和下载。
- Skill 底座：SkillRun、显式启动、补参、运行卡片。
- Windows 打包和内网更新代码级准备。

需要继续收口：

- 将旧 `derived/` source repo 迁移到 `_preprocessed/.../gbrain-ready/`。
- 建立独立 preprocessor Skills 和质量回归。
- 删除/重跑旧 `customer-reference` 生成物，使用 GBrain 原生客户情报能力重跑。
- 补齐文件预览、区域级引用、置信度、时间戳回链和项目/客户真实样本回归。
- 用真实业务 Skill 做端到端验收。

## 12. 成功标准

Project_R 第一版可正式投放使用，需要满足：

- 普通用户能稳定登录、聊天、保存和恢复会话。
- `/query` 在个人、项目、客户工作区严格按 source scope 返回可信答案和 citation。
- 项目和客户文件录入不会污染公司知识库。
- GBrain-ready Markdown、manifest、审计和通知能追踪每次录入。
- 管理员能看到 GBrain 状态、质量回归、失败任务和审核项。
- 测试不会污染真实用户、真实工作区、真实 source。
- 客户端可在内网安装、升级和连接后端。
