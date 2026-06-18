# AGENTS.md — Project_R Agent 工作规则

## 三阶段工作流

### 阶段一：分析问题
**声明格式**：【分析问题】

**必须做的事**：
- 深入理解需求本质
- 检索市面上是否已有成熟方案,可以学习借鉴思路,不要从零开始创造
- 搜索所有相关代码,是否已有可复用功能/代码
- 识别问题根因
- 发现架构问题
- 如果有不清楚的，请向我收集必要的信息
- 提供 1~3 个解决方案（如果方案与用户想达成的目标有冲突，则不应该成为一个方案）
- 评估每个方案的优劣

**融入的原则**：
- 系统性思维：看到具体问题时，思考整个系统
- 第一性原理：从功能本质出发，而不是现有代码
- DRY 原则：发现重复代码必须指出
- 长远考虑：评估技术债务和维护成本

**绝对禁止**：
- 修改任何代码
- 急于给出解决方案
- 跳过搜索和理解步骤
- 不分析就推荐方案

### 阶段二：细化方案
**声明格式**：【细化方案】

**前置条件**：
用户明确选择了方案（如："用方案 1"、"实现这个"）

**必须做的事**：
列出变更（新增、修改、删除）的文件，简要描述每个文件的变化。

### 阶段三：执行方案
**声明格式**：【执行方案】

**必须做的事**：
- 严格按照选定方案实现
- 修改后运行验证（见"阶段执行规则"中的验证门槛）

**绝对禁止**：
- 提交代码（除非用户明确要求）


### 阶段切换规则
1. **默认阶段**：收到新问题时，始终从【分析问题】开始
2. **切换条件**：只有用户明确指示时才能切换阶段
3. **禁止行为**：不允许在一次回复中同时进行两个阶段

### 例外规则
当用户请求非常明确且可直接执行时（如"把 X 改成 Y"、"删除文件 Z"、"运行命令 W"），可跳过分析和细化阶段，直接进入执行阶段，但仍需在回复开头声明【执行方案】并简要说明变更内容。

### 每次回复前的强制检查
- [ ] 我在回复开头声明了阶段吗？
- [ ] 我的行为符合当前阶段吗？
- [ ] 如果要切换阶段，用户同意了吗？

## 备注
- 使用 utf-8 编码
- 始终使用简体中文回复

---

## 文档分工

| 文件 | 职责 |
|---|---|
| `AGENTS.md` | Codex / 通用 Agent 工作规则，本文件 |
| `CLAUDE.md` | Claude Code 工作规则镜像；必须与 `AGENTS.md` 对齐，冲突时以 `AGENTS.md` 为准 |
| `docs/product/Project_R PRD.md` | 产品范围、目标用户、长期能力边界 |
| `docs/milestones/Project_R 开发流程.md` | 阶段顺序、任务清单、完成标志、实现状态，checklist 的唯一维护处 |
| `docs/milestones/Project_R 开发流程V2.0.md` | 下一阶段产品基座精修主计划：Chat、知识库查询、检索与基础 Agent |
| `docs/product/Project_R 业务工作流清单.md` | 企业业务 Skill 候选清单与实现状态 |
| `docs/design/ui-design-language.md` | 前端视觉语言、选中态、控件尺寸和 UI 修改约束 |
| `docs/agents/skills-design.md` | 业务 Skill 设计规范 |
| `docs/product/gbrain-feature-inventory.md` | GBrain 原生功能盘点矩阵 |
| `docs/specs/gbrain-ingest-workflow.md` | 原始资料进入 GBrain source 的导入、提炼、审核和索引流程 |
| `docs/milestones/gbrain-adaptation-progress.md` | GBrain 适配进度、未闭环项和下一步顺序 |
| `CONTEXT.md` | 项目领域术语表，Agent 理解业务概念的参考 |

当前仓库核心产品文档以 `docs/product/`、`docs/milestones/`、`docs/specs/`、`docs/validation/`、`docs/design/` 和 `docs/operations/` 下的版本为准。当代理工作规则发生变化时，必须同步更新 `AGENTS.md` 与 `CLAUDE.md`；当产品范围或阶段任务变化时，同步更新 PRD 或开发流程。涉及前端视觉的改动，必须先查看 `docs/design/ui-design-language.md` 并复用既有 token。

---

## 项目结构

```text
Project_R/
├── .agents/skills/          # mattpocock/skills 已安装工程/生产力 skills
├── AGENTS.md                # Codex / 通用 Agent 工作规则
├── skills-lock.json         # skills 版本锁文件
├── backend/                 # FastAPI 后端
│   ├── api/                 # HTTP 路由层
│   ├── app/features/        # 业务模块（chat、knowledge、workspace 等）
│   ├── app/shared/          # 共享能力（LLM 客户端、web search 等）
│   ├── models/              # SQLAlchemy 数据模型
│   ├── routers/             # 附加路由（文件预览等）
│   ├── skills/builtin/      # 官方内置业务 Skill
│   ├── skills/preprocessors/# 文件类型预处理 Skill
│   └── tests/               # pytest 测试套件
├── frontend/                # Electron + React + Vite + TypeScript + Jotai
│   └── src/renderer/
│       ├── features/        # 业务模块（chat、workspace、admin 等）
│       ├── shared/          # 共享组件、API 客户端、工具函数
│       ├── pages/           # 页面级组件（LoginPage、AppPage、OnboardingPage）
│       └── app/             # 入口与壳层（App.tsx、AppShell.tsx）
├── docs/                    # 产品、里程碑、ADR、设计、规格、运维文档
└── scripts/                 # 项目维护脚本
```

---

## 开发理念

Project_R 后续开发按"可验证竖切片"推进，而不是按目录堆功能。

1. 先让一个真实业务场景跑通，再扩展通用能力。
2. 后端是业务能力中心，前端是安全、轻量、可配置的桌面入口。
3. 业务层只依赖统一接口，不直接绑死某个 LLM 厂商、模板库或前端页面。
4. 每个阶段都必须有清晰完成标志；未验证的代码只能写实现状态，不能勾 checklist。
5. 默认优先做小型可运行测试，真实 LLM API 调用不进入默认单元测试。

四条长期主线：

| 主线 | 目标 |
|---|---|
| 对话底座 | 登录用户稳定发起、保存、恢复多轮对话 |
| 知识底座 | 系统能可信引用公司文档回答问题 |
| 文件与 Skill 底座 | 用户通过显式入口或后续自然语言意图识别生成标准业务文件或流程输出 |
| 管理与交付底座 | 管理员可维护系统，员工可稳定使用 |

---

## Vibecoding 架构护栏

- 每次新增功能前，必须先判断功能归属目录。后端新功能默认进入 `backend/app/features/<feature>/...` 或 `backend/app/shared/...`；`backend/api/` 只允许保留薄路由。前端新功能默认进入 `frontend/src/renderer/features/<feature>/...` 或 `frontend/src/renderer/shared/...`；`pages/` 只做页面组装，不堆业务逻辑。
- 禁止在根目录、`backend/` 根、`frontend/src/` 根或 `renderer/` 根随手创建杂散文件；确需新增目录时，必须说明归属 feature、调用方和验证方式。
- 文件大小红线：超过 400 行评估是否应拆分；超过 800 行原则上不堆功能；超过 1500 行必须优先提出拆分计划。
- API 层必须保持薄：不得把文件系统编排、GBrain/LLM 调用、复杂状态机、批处理、权限策略细节直接堆进路由函数。
- 每次 Agent 交付必须说明修改文件、验证命令、验证结果和未验证风险。
- 禁止"顺手优化"：一个任务只处理一个明确目标。
- 对 AI 生成代码的默认要求：先读相关代码和文档，遵守现有命名、权限、真实数据隔离和 GBrain 边界；不得编造测试结果。

---

## 代码结构与可维护性准则

> Gary 的核心要求：代码必须**框架清晰、可控、易于后期维护与功能变更**。结构清晰永远优先于功能数量。Agent 在按开发流程推进时，**不得以"把代码堆进现有文件"的方式交付功能**。Gary 不是系统架构专家，把控代码结构是 Agent 的责任。

### 总原则
- 结构清晰优先于功能堆叠：宁可多花一步建立清晰边界，也不在已臃肿的文件/函数上继续叠加。
- 每块功能都应**可替换、可删除、可测试**，影响面可预测。

### 1. 架构优先（先定接缝，再写代码）
- 动手前先回答三问：这段代码的**落点模块**是哪一个？它通过**什么接口**被调用？将来**替换/扩展**时改哪里？
- 新行为优先放到清晰的接口/接缝之后；同类扩展（新模型、新文档格式、新工具）通过**实现接口或注册表**接入，而不是在调用点堆 if/else。

### 2. 单一职责与归属
- 一个文件/模块/函数只承担一类职责；后端落 `app/features` 或 `app/shared`，前端落 `features` 或 `shared`，`pages` 只做组装。
- 路由、业务、数据、UI、状态各层职责分明，不互相渗透。

### 3. 反"上帝文件"（硬约束）
- 严守体量红线：>400 行评估拆分、>800 行不再加新功能、>1500 行必须先拆。
- 触碰已超红线的大文件时，**默认动作是"抽离"**，使其净行数下降或持平；禁止"反正已经很大了就再加一点"。
- 大组件按子组件/hook 拆分；大路由把逻辑下沉到 feature 服务；大服务按用例拆分。

### 4. 接缝优于耦合（可替换）
- 业务层只依赖统一接口，不绑死某一厂商/库/页面（LLM provider、文档渲染、知识库后端皆然）。
- 厂商特定细节（如 SSE 格式、SDK 形状）收敛在适配层，不泄漏到业务层。

### 5. 薄路由 / 业务在 feature 层
- API/IPC 层只做参数校验与转发；文件编排、LLM/GBrain 调用、状态机、批处理、权限策略放 feature 层。

### 6. 删除即清理，不留投机代码
- 不保留不可达分支、被注释的旧实现、"以后可能用得上"的空壳；功能下线时连带清掉其代码与配置。

### 7. 变更可控、可追溯
- 一个任务只解决一个明确目标，禁止顺手重构无关代码。
- 每次交付声明：改了哪些文件、落点是否正确、是否抽离了大文件、验证命令与结果、未验证风险。

### 8. 维护性交付清单（每个功能任务的完成定义 DoD）
- [ ] 落点正确（在所属 feature/模块内）。
- [ ] 未增大上帝文件（触碰大文件时以抽离为主）。
- [ ] 同类扩展通过接口/注册表接入，无复制粘贴调用点。
- [ ] 路由/IPC 保持薄。
- [ ] 无死代码、无投机空壳。
- [ ] provider/vendor 无关。
- [ ] 附验证（`pytest` / `bun run typecheck` / 关键 E2E）且不污染真实数据。

---

## 开发红线

- 所有路径必须可迁移到 Mac mini，禁止写死 `D:/...`、`C:/...` 等绝对路径。
- 后端路径用 `pathlib.Path` 或跨平台路径 API；文本读写显式使用 `encoding="utf-8"`。
- 环境变量写入 `.env.example`；真实 `.env`、数据库、API Key、生成文件不入 Git。
- API Key 只允许存在于后端环境变量中，绝不进入前端、日志、响应体或文档示例。
- 前端请求层不得写死 `localhost`；后端地址由 `shared/state/server.ts` 管理并持久化。
- 员工前端不得暴露 API Key 或多 Key 配置。
- Proma 参考按三层判断：**表现层**（布局/圆角/间距等）默认允许强参考；**产品交互层**（功能入口/工作区切换等）允许参考但必须映射到当前 PRD 和权限边界；**架构执行层**（客户端执行链路/IPC 编排/API Key 管理等）默认禁止迁移。原则：Proma shell first, Project_R core always。
- 已获 Gary 授权后，Agent 可以为项目运行必要的依赖安装命令。

---

## 阶段执行规则

- 开发任务以 `docs/milestones/Project_R 开发流程.md` 为准。
- 每个阶段先做最小竖切片，再补权限、错误、日志、跨平台与体验。
- 已完成且验证的功能，必须同步勾选 checkpoint。
- 未验证、只完成设计、只完成后端但未接前端的任务保持未勾选。
- 新增或修改业务 Skill 后，同步更新 `docs/product/Project_R 业务工作流清单.md`。

默认验证门槛：

- 后端改动：必须使用项目虚拟环境运行相关 `pytest`，命令格式为 `cd backend && .\venv\Scripts\python.exe -m pytest tests/<target>.py`；不要用系统 `python -m pytest`。当前环境差异记录见 `docs/operations/python-environment-inventory.md`。
- 前端改动：运行 `cd frontend && bun run typecheck`；涉及打包、路由或构建配置时补跑 `bun run build`。
- 跨端链路：说明后端地址、测试账号、是否使用真实 LLM Key、是否需要手工确认。

---

## 真实数据与测试隔离规则

- 不得私自创建、删除、禁用或修改真实 `backend/app.db` 中的用户、真实工作区、成员关系、客户/项目 source 或用户私人工作台；只有 Gary 明确授权清理或迁移时才可操作。
- 功能测试必须优先使用临时 SQLite DB、临时 workspace root、测试夹具或 monkeypatch 后的路径；不得让自动化测试污染 `backend/app.db`、`backend/workspace_data/user/`、`backend/workspace_data/project/`、`backend/workspace_data/customer/` 或正式 GBrain source。
- 测试需要临时账号、临时工作区、临时 GBrain source、临时 OAuth client、临时文件或临时索引时，命名必须带明确测试前缀，并在测试结束后清理；无法自动清理时，最终回复必须列出残留路径、DB 记录或 source id。
- 真实清理必须先说明影响范围，包含会删除的 DB 记录、磁盘目录、GBrain source/client 和不会触碰的对象；执行后必须做清理后验证。
- 不得把清理缓存、测试残留或历史数据的任务扩展成业务代码删除、批量格式化或无关重构。

---

## 业务文件容器规则

- 需要长期保存、共享、权限治理、审计、入库、复盘或被项目/客户知识库引用的业务文件，只能进入项目工作区或客户工作区的文件面板。
- 个人工作台只保留对话、提示词上下文、会话临时附件和本地导出/下载；不得作为个人文件面板、个人知识库或个人 GBrain source。
- 个人工作台允许运行轻量业务 Skill / Agent 生成类任务（起草、改写、填写模板等），但输出默认只作为本轮结果展示，可复制或下载到本地；不得保存到项目/客户资料的跨工作区动作。
- 项目/客户工作区里 Skill / Agent 输出须用户确认保存后才写入当前工作区文件面板，默认位置为 `99-未归档文件`；保存不等于自动入库 GBrain。
- Agent 不得把本机选择文件、会话附件或导出文件隐式保存到个人工作台、项目资料或客户资料。

---

## GBrain 边界规则

### 职责边界
Project_R 只做源文件保管、粗处理/预处理、权限审计、后端保存、查询转发和 UI 展示；真正知识库系统是 GBrain。后续 Agent 不得把 Project_R 做成 GBrain schema、entity enrichment、graph、timeline、query、think 或 citation 的替代实现。

### 预处理产物架构
- 用户源文件目录只保存原始文件；不得在用户源文件目录下新增 `derived/`。
- 预处理过程文件统一写入 `backend/workspace_data/_preprocessed/.../runs/`，最终 GBrain-ready Markdown 写入 `_preprocessed/.../gbrain-ready/`，该目录才是 GBrain source repo 目标。
- 源文件删除不自动清理 GBrain-ready 产物和 GBrain 知识库；需要管理员显式执行清理。
- 源文件 hash 变化后不自动重跑预处理；只标记 `needs_repreprocess`，由用户显式点击"录入"后创建新 run。
- 预处理成功写入 `gbrain-ready/` 后可自动触发当前 source 的 GBrain sync；不得自动触发 Entity Enrichment、graph merge、citation-fixer 等复杂写操作。
- DeepSeek 用于纯文本资料处理；PDF、截图、图纸、设计图片使用 MiMo V2.5；会议音频/视频先走转写脚本。

### 录入权限
- 待处理状态包括 `new`、`source_changed`、`failed_retryable`、`pending_capability_now_supported`；`synced`、`processing`、`source_deleted`、`failed_non_retryable`、`ignored` 不默认处理。
- 第一版人工状态动作只提供"忽略录入 / 取消忽略"和"重新录入此文件"；其他状态由 manifest、hash、run 结果和 GBrain sync 结果自动维护。
- 系统管理员和工作区管理员可录入文件夹和单文件；普通项目成员第一版只允许录入自己上传的单个文件。
- 客户工作区仅系统管理员和客户工作区管理员可录入；公司全局知识库仅系统管理员可录入。
- 文件面板点击"录入"时默认处理当前打开路径并递归子文件夹，必须二次确认。

### `/query` Source Scope
- 个人工作台 `/query` 只查询 `company-wiki`，不得查询项目或客户 source。
- 项目工作区 `/query` 查询 `company-wiki + 当前项目 source`。
- 客户工作区 `/query` 只查询客户情报 GBrain 数据，不叠加 `company-wiki` 或项目 source。

### 客户情报
- `workspace_data/customer/` 是 CRM 客户画像资料根，固定路径为 `customer/CRM/raw/`，GBrain-ready 固定为 `_preprocessed/customer/crm/gbrain-ready/`。
- 客户情报是受限业务情报，不得写入 `company-wiki`，不得默认与公司全局知识库联合查询。
- 客户情报目标是通过 GBrain Entity Enrichment 自动建立 People/Company/Project Graph。

---

## 当前项目状态

当前开发阶段已完成 Phase 1-20 主体功能（对话底座、GBrain 知识库、工作区文件管理、通知中心、设置界面、客户端更新等）；具体进度以 `docs/milestones/Project_R 开发流程.md` 为准。

API 验证见 `backend/tests/` 测试文件，管理员默认账号 `admin / Project_R_2026`。

---

## 后端约定

后端采用 Python FastAPI + SQLite：

- `backend/main.py`：FastAPI 应用入口，注册路由并启动时初始化数据库。
- `backend/api/`：HTTP 路由层。`api/rag.py` 实际为 GBrain 管理 API。
- `backend/app/features/`：业务模块（chat、knowledge、workspace、preprocessing、skills、auth、notifications、documents、agents、prompts）。
- `backend/app/shared/`：共享能力（LLM 客户端、时间工具、web search）。
- `backend/models/`：SQLAlchemy 数据模型（约 14 个，含 User、ChatSession、Workspace、Notification 等）。
- `backend/routers/`：附加路由（项目文件预览等）。
- `backend/skills/builtin/`：官方内置业务 Skill。
- `backend/skills/preprocessors/`：文件类型预处理 Skill。

LLM Provider 约定：

- 业务层只调用统一 LLM Provider 接口，不直接依赖某一家厂商 SDK。
- `model_profile` 是用户可见的后端白名单模型配置档，不等于 API Key。
- `/health/llm` 只返回已配置 provider/profile 的可用状态、模型名、描述与 Key 数量，严禁返回 Key 明文。
- 思考模式由前端发送 `thinking` 布尔值，后端按 provider 生成实际 payload。
- 每个 Provider 内部独立管理多个 API Key，使用 Round-Robin 轮询，自动容错。
- 默认测试使用 mock LLM，不调用真实 Claude / OpenAI / DeepSeek API。

---

## 前端约定

- 使用 Electron + React + Vite + TypeScript + Jotai。
- Electron 主进程保持安全默认值：`contextIsolation: true`、`nodeIntegration: false`、最小化 `preload`。
- Electron 窗口使用软件内窗口控制，不得恢复系统主菜单栏。
- 路由保留 `/login`、`/app`、`/settings`、`/onboarding`（基于 hash，非 react-router）。
- 登录认证状态统一放在 `features/auth/state.ts`（含 Token、当前用户、登录写入、登出清理）。
- API client 自动携带 JWT Token；遇到 401 必须触发本地登出或清理认证状态。
- `/app` 主界面必须受认证保护；未登录或 Token 失效时跳回 `/login`。
- 状态管理集中在各 `features/*/state.ts` 及 `shared/state/` 中。
- 提示词系统分三类：Project_R 内置提示词（系统只读）、公司预设提示词（后端管理）、用户自定义提示词（本机 Electron userData）。
- `backend/prompt_presets/global-base-prompt.md` 是后端强制注入的底层规则，system prompt 组合优先级：全局底层规则 → 会话提示词 / Agent 模式提示 → 会话临时附件 → 知识库/项目资料 → 用户问题。
- Chat / Agent 产品边界当前冻结为**显式路由优先**：`core/intent.py` 默认只返回 `chat`；知识库问答必须使用 `/query ...`；业务 Skill 须手动选择启动。
- 工作区是项目资料容器，代码内部继续使用 `workspace` 命名；公司项目默认对所有有效用户开放；隐藏项目才限制访问。

---

## Agent Skills

本项目基于 mattpocock/skills，通过 `skills-lock.json` 管理版本。

| 分类 | Skills |
|---|---|
| 工程 | `diagnose`、`grill-with-docs`、`improve-codebase-architecture`、`prototype`、`setup-matt-pocock-skills`、`tdd`、`to-issues`、`to-prd`、`triage`、`zoom-out` |
| 生产力 | `caveman`、`grill-me`、`handoff`、`write-a-skill` |

Issue tracker、triage labels、domain docs 见 `docs/agents/`。
