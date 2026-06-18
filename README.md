# Project_R 维护入口地图

本文件用于帮助 Gary 在后续测试、更新和维护 Project_R 时快速找到该改哪里。原则是：不移动真实代码目录，只在这里建立维护索引，避免破坏 import、路由、构建和运行路径。

**当前代码分层（大拆分后）**：后端 `api/` 薄路由 + `app/features/` 业务 + `app/shared/` 共享；前端 `pages/` 组装 + `features/` 业务 + `shared/` 共享。下文表格按此结构索引，不再引用已删除的 `backend/core/`、`frontend/.../components/`（根级）、`atoms/`、`api/`（renderer 根级）等旧路径。

## 最常改的目录

| 路径 | 作用 | 适合 Gary 自定义吗 | 常见修改 |
|---|---|---|---|
| `docs/product/` | PRD、产品边界、业务工作流和 GBrain 能力盘点 | 是，但只改 Project_R 自有文档 | 更新需求、业务范围、Skill 候选清单 |
| `docs/milestones/` | 阶段计划、开发流程、迭代进度和历史清理盘点 | 是 | 更新阶段进度、下一步计划、完成状态 |
| `docs/specs/` | 具体功能方案、实现规格、GBrain ingest 流程和提示词模板 | 是 | 写功能方案、验收标准、实现说明 |
| `docs/validation/` | 测试说明、手工验收、Windows 联调和验收报告 | 是 | 写测试清单、故障排查、验收记录 |
| `docs/design/` | UI 设计语言、设计稿和视觉参考 | 是 | 更新视觉规范、设计参考、界面调整说明 |
| `docs/operations/` | 安装、运行、维护和 GBrain 运维手册 | 是 | 写部署、维护、运行排查步骤 |
| `backend/prompt_presets/` | 后端强制注入或预留的提示词文件 | 是，尤其是 `global-base-prompt.md` | 填写公司全局底层规则、统一业务背景、回答边界 |
| `backend/skills/builtin/` | Project_R 官方内置业务 Skill | 是，但建议一次只改一个 Skill | 新增/修改业务 Skill、输出格式、字段要求 |
| `backend/skills/preprocessors/` | 文件类型预处理 Skill 元数据 | 是，与 preprocessing 实现对齐 | 新文件格式接入时的 SKILL.md 与路由声明 |
| `.agents/skills/` | Codex/Agent 本地工作技能说明 | 是，偏开发协作 | 修改 Agent 如何分析、提问、写方案、生成文档 |
| `.claude/skills/` | 历史 Claude 系 Agent 本地技能说明 | 不再主动维护 | 仅在仍使用 Claude Code 时参考 |
| `backend/templates/` | 后端文件生成模板 | 是 | 放公司 Word/Excel/PPT 模板，后续接入正式模板渲染 |
| `backend/workspace_data/global/company-wiki/` | GBrain 公司知识库原始资料区 | 是，维护 `raw/` 原始文件 | 放入 raw 原始资料；GBrain-ready 产物在 `_preprocessed/company/company-wiki/gbrain-ready/` |
| `backend/workspace_data/_preprocessed/` | 预处理过程文件与 GBrain-ready Markdown | 不建议手改 derived 产物 | 各 source 的 runs/、gbrain-ready/；录入/sync 由软件触发 |
| `backend/workspace_data/` | 工作区/项目/客户资料真实存储 | 可通过软件上传维护，不建议直接手改 | `project/`、`customer/`、`user/` 等业务目录 |

## 后端功能目录

| 路径 | 作用 | 修改风险 | 说明 |
|---|---|---|---|
| `backend/main.py` | FastAPI 应用入口 | 高 | 路由注册、启动时初始化数据库与 GBrain maintenance worker |
| `backend/api/` | HTTP 接口层（薄路由） | 中高 | 只做参数校验与转发；业务逻辑在 `app/features/` |
| `backend/api/chat.py` | 聊天、会话、附件、流式发送 | 高 | 转发到 `app/features/chat/`（send/stream/export/feedback 等） |
| `backend/api/workspaces.py` | 工作区、项目文件、录入、图谱 | 中高 | 转发到 `app/features/workspaces/`（files/、ingest/、meetings/） |
| `backend/api/rag.py` | GBrain 管理与知识 API | 高 | query/sync/doctor、source 状态、知识审核与质量报告；`knowledge_router` 供浏览器/证据 |
| `backend/api/skills.py` | Skill API | 中 | Skill 列表、匹配、启动、补参、运行状态 |
| `backend/api/admin.py` | 管理员 API | 中 | 用户管理、审计日志、知识审核等 |
| `backend/api/auth.py` | 登录认证 | 中 | JWT 签发与 `/auth/me` |
| `backend/api/documents.py` | 文档生成与下载 | 中 | 转发到 `app/features/documents/` |
| `backend/api/prompts.py` | 提示词预设 | 中 | 公司预设 prompt 管理 |
| `backend/api/notifications.py` | 通知中心 | 中 | 转发到 `app/features/notifications/` |
| `backend/api/health.py` | 健康检查 | 低 | 含 `/health/llm` provider 可用状态 |
| `backend/app/features/` | 业务模块 | 高 | 按 feature 拆分，路由不得堆复杂逻辑 |
| `backend/app/features/chat/` | 对话底座 | 高 | `send_message_service.py`、`stream_service.py`、附件、意图、Skill 派发、音频理解 |
| `backend/app/features/workspaces/` | 工作区与项目文件 | 中高 | `files/` 上传/回收区/生命周期；`ingest/` 录入 executor；`meetings/` 会议转写 |
| `backend/app/features/workspaces/files/service.py` | 文件面板核心服务 | 中高 | 上传大小限制、权限、回收区、路径解析 |
| `backend/app/features/knowledge/` | 知识库与 GBrain 边界 | 高 | `browser.py`、`evidence.py`、`sources.py`；GBrain 细节在 `gbrain/` 子包 |
| `backend/app/features/knowledge/gbrain/adapter.py` | GBrain 服务 adapter | 高 | health、source 状态、query/sync/doctor、source 路径解析 |
| `backend/app/features/knowledge/gbrain/ingest.py` | 公司 wiki 导入编译 | 高 | raw → gbrain-ready、manifest、本地 Git |
| `backend/app/features/knowledge/gbrain/maintenance/` | GBrain 后台维护 | 高 | citation fixer、dream cycle、contradiction probe、worker |
| `backend/app/features/preprocessing/` | 文件类型预处理 | 高 | PDF/DOCX/图片/邮件/会议音视频等结构化提取，写入 `_preprocessed/` |
| `backend/app/features/skills/` | Skill 加载与执行 | 高 | `runner.py` 匹配加载；`execution.py` / `dispatcher.py` 执行输出 |
| `backend/app/features/documents/` | 业务文件生成 | 中高 | `generation.py`、`renderer.py`、`renderers/`（docx/xlsx/pptx/pdf/eml） |
| `backend/app/features/agents/` | Agent 运行事件 | 中 | run 序列化与事件结构 |
| `backend/app/features/auth/` | 认证辅助 | 中 | 系统账号等 |
| `backend/app/features/notifications/` | 通知服务 | 中 | 写入与推送通知记录 |
| `backend/app/features/prompts/` | System prompt 组合 | 中 | 全局底层规则与各层 prompt 拼装 |
| `backend/app/shared/` | 跨 feature 共享 | 高 | LLM、web search、时间工具等 vendor 无关能力 |
| `backend/app/shared/llm/client.py` | LLM Provider 抽象 | 高 | Claude/OpenAI-compatible/DeepSeek/MiMo、多 Key 轮询 |
| `backend/models/` | SQLAlchemy 数据模型 | 高 | User、ChatSession、Workspace、Message、SkillRun、AuditLog 等 |
| `backend/routers/` | 附加路由 | 中 | 如 `project_preview.py` 文件预览 |
| `backend/skills/builtin/` | 官方内置业务 Skill | 是 | 每个 Skill 一个目录，含 `SKILL.md` |
| `backend/skills/preprocessors/` | 文件预处理 Skill 元数据 | 是 | 与 `app/features/preprocessing/` 实现对应 |
| `backend/tests/` | pytest 测试套件 | 是，推荐经常补 | 权限、上传、GBrain、Skill、chat 等；改逻辑后补对应用例 |
| `backend/requirements.txt` | Python 依赖声明 | 谨慎 | 新增解析/渲染库时必须同步 |

## 前端功能目录

| 路径 | 作用 | 修改风险 | 说明 |
|---|---|---|---|
| `frontend/src/renderer/app/` | 应用入口与壳层 | 中高 | `main.tsx` 挂载、`App.tsx` hash 路由（`/login`、`/app`、`/onboarding`）、`AppShell.tsx` 窗口框架 |
| `frontend/src/renderer/pages/` | 页面级组件 | 中高 | `LoginPage`、`AppPage`、`OnboardingPage`；只做页面组装，业务逻辑下沉到 `features/` |
| `frontend/src/renderer/pages/AppPage.tsx` | 主工作台页面 | 高 | 组装聊天、工作区、设置等 feature；复杂 UI 逐步下沉到 `features/chat/components/` |
| `frontend/src/renderer/features/` | 业务功能模块 | 中~高 | 按 feature 拆分：`chat`、`workspace`、`auth`、`settings`、`admin`、`knowledge`、`notifications`、`prompts`、`skills`、`updates` |
| `frontend/src/renderer/features/chat/` | 对话底座 | 高 | 消息流、Composer、附件、Skill/Agent 卡片；含 `api.ts`、`state.ts`、`components/`、`hooks/`、`styles/` |
| `frontend/src/renderer/features/chat/components/AppWorkspaceChrome.tsx` | 主聊天工作台 UI 壳 | 高 | 会话列表、消息区、输入区、工作区侧栏与设置入口 |
| `frontend/src/renderer/features/workspace/` | 工作区与项目文件 | 中高 | `WorkspaceFilePanel.tsx`、上传/拖拽、回收区、文件预览、知识图谱 overlay |
| `frontend/src/renderer/features/workspace/components/WorkspaceFilePanel.tsx` | 项目文件面板 | 中高 | 上传、拖拽、回收区、恢复、永久删除、刷新项目索引 |
| `frontend/src/renderer/features/settings/` | 设置 | 高 | `SettingsModal.tsx`、通用偏好、提示词入口、管理员后台入口 |
| `frontend/src/renderer/features/settings/components/SettingsModal.tsx` | 设置弹窗 | 高 | 通用设置、提示词、管理员后台、服务器连接 |
| `frontend/src/renderer/features/admin/` | 管理员后台 UI | 中高 | GBrain 状态仪表盘、知识审核、用户管理等面板 |
| `frontend/src/renderer/features/knowledge/` | 知识库浏览与证据 | 中 | 知识浏览器、source 证据展示与筛选 |
| `frontend/src/renderer/features/auth/` | 登录认证 | 中 | `state.ts`（Token、当前用户、登出清理）、`api.ts` |
| `frontend/src/renderer/shared/` | 跨 feature 共享 | 中 | API 客户端、全局样式、通用组件、图标、服务器地址等状态 |
| `frontend/src/renderer/shared/api/client.ts` | HTTP 请求基座 | 中高 | JWT 携带、401 触发登出、统一请求封装 |
| `frontend/src/renderer/shared/api/types.ts` | 共享 API 类型 | 中 | 跨 feature 复用的后端响应结构；变更后需同步各 feature `api.ts` |
| `frontend/src/renderer/shared/state/server.ts` | 后端地址状态 | 中 | 持久化服务器 URL；业务代码不得写死 `localhost` |
| `frontend/src/renderer/shared/styles/global.css` | 全局样式入口 | 中 | 聚合 `base.css`、`shell.css`、`dialogs.css` 及各 feature 的 `styles.css` |
| `frontend/src/main/` | Electron 主进程 | 高 | 窗口、`preload` 注册、本机用户提示词、客户端更新下载 |
| `frontend/src/preload/` | Electron preload | 高 | `contextIsolation` 下暴露的最小 IPC 桥，禁止扩大 node 权限 |

## 配置与环境

| 路径 | 作用 | 是否可改 | 注意 |
|---|---|---|---|
| `backend/.env` | 本机真实后端配置 | 是，但不入 Git | API Key、数据库路径、模型 profile、GBrain 配置 |
| `backend/.env.example` | 后端配置模板 | 是 | 新增环境变量时同步写这里 |
| `frontend/.env.development` | 前端开发默认后端地址等 | 是 | 不要在请求代码里写死 localhost |
| `package.json` / `frontend/package.json` | Node/Bun 依赖和脚本 | 谨慎 | 新增前端依赖或脚本时修改 |
| `backend/requirements.txt` | Python 依赖 | 谨慎 | 新增后端依赖后要安装并跑测试 |
| `.gitignore` | Git 忽略规则 | 谨慎 | 确保数据库、上传文件、生成文件、缓存不进 Git |

## 运行生成物和缓存，不建议手动修改

| 路径 | 作用 | 建议 |
|---|---|---|
| `backend/venv/` | Python 虚拟环境 | 不手改；用 pip/requirements 管理 |
| `node_modules/` | 根目录 Node 依赖 | 不手改；用 npm/bun 安装 |
| `frontend/node_modules/` | 前端 Node 依赖 | 不手改；用 npm/bun 安装 |
| `backend/__pycache__/`、各级 `__pycache__/` | Python 缓存 | 不手改，可删除重建 |
| `frontend/dist/` | 前端构建产物 | 不手改；由 `bun run build` 生成 |
| `backend/workspace_data/global/company-wiki/` | 公司知识库 raw 原始资料 | raw 可手动投喂；勿在源目录下写 derived |
| `backend/workspace_data/_preprocessed/` | 预处理与 gbrain-ready 产物 | 不手改；由录入/预处理 run 写入 |
| `backend/workspace_data/_gbrain/` | GBrain runtime 数据与 manifest | 不手改；由 GBrain sync 与 adapter 维护 |
| `backend/generated_files/` | AI 生成的下载文件 | 不手改；由文件生成接口和清理逻辑管理 |
| `backend/session_attachments/` | 会话临时附件 | 不手改；删除会话时应自动清理 |
| `backend/workspace_data/*/.trash/` | 工作区回收区 | 优先通过软件恢复/永久删除 |
| `app.db`、`backend/app.db` | SQLite 数据库 | 不直接编辑；用 API 或迁移逻辑修改 |

## 常见任务该从哪里开始

| 任务 | 先看哪里 | 验证方式 |
|---|---|---|
| 改上传文件大小限制 | `backend/app/features/workspaces/files/`、`frontend/src/renderer/features/workspace/components/WorkspaceFilePanel.tsx` | `backend/tests/test_workspace_files.py` + `bun run typecheck` |
| 改工作区文件权限 | `backend/app/features/workspaces/permissions.py`、`backend/api/workspaces.py` | `backend/tests/test_workspace_files.py` 等 workspace tests |
| 改回收区逻辑 | `backend/app/features/workspaces/files/lifecycle.py`、`frontend/src/renderer/features/workspace/components/WorkspaceFilePanel.tsx` | 上传、删除、恢复、永久删除手工验收 |
| 让 Word/PDF/Excel 可被项目问答引用 | `backend/app/features/preprocessing/`、`backend/app/features/workspaces/ingest/` | 新增 preprocessing 测试 + 项目对话验收 |
| 改 GBrain 查询/source 范围 | `backend/app/features/knowledge/gbrain/adapter.py`、`backend/api/rag.py` | `backend/tests/test_rag_api.py`、`test_gbrain_*` |
| 改 Global Base Prompt | `backend/prompt_presets/global-base-prompt.md` | 发普通聊天、项目聊天、Skill 触发检查是否生效 |
| 改聊天消息排版 | `frontend/src/renderer/features/chat/styles/`、`frontend/src/renderer/features/chat/components/` | `bun run build` + Electron 手工看界面 |
| 改设置页 | `frontend/src/renderer/features/settings/components/SettingsModal.tsx`、`frontend/src/renderer/features/settings/styles.css` | `bun run build` + 登录管理员/普通用户检查 |
| 新增业务 Skill | `backend/skills/builtin/`、`docs/agents/skills-design.md` | Skill 列表、匹配、启动、补参、输出文件测试 |
| 新增文件预处理能力 | `backend/skills/preprocessors/`、`backend/app/features/preprocessing/` | 对应 `test_*_preprocess.py` + 录入验收 |
| 更新开发进度 | `docs/milestones/Project_R 开发流程.md` | 勾选必须对应已验证功能 |
| 更新产品范围 | `docs/product/Project_R PRD.md` | 保持与开发流程一致 |
| 更新 Agent 工作规则 | `AGENTS.md` | 当前只维护 AGENTS.md |

## 修改前后建议流程

1. 先在本文件定位功能归属。
2. 读对应 PRD / 开发流程段落，确认当前阶段是否允许改。
3. 修改最小相关文件，不顺手重构无关代码。
4. 后端改动跑：`cd backend && .\venv\Scripts\python.exe -m pytest tests/<target>.py`
5. 前端改动跑：`cd frontend && bun run typecheck`（涉及打包时补 `bun run build`）
6. 涉及 UI、上传、文件下载、RAG 引用时，再做 Electron 手工验收。
7. 验证通过后，同步更新 `docs/milestones/Project_R 开发流程.md`。
