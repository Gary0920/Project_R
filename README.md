# Project_R 维护入口地图

本文件用于帮助 Gary 在后续测试、更新和维护 Project_R 时快速找到该改哪里。原则是：不移动真实代码目录，只在这里建立维护索引，避免破坏 import、路由、构建和运行路径。

## 最常改的目录

| 路径 | 作用 | 适合 Gary 自定义吗 | 常见修改 |
|---|---|---|---|
| `references/` | PRD、开发流程、业务工作流、V3.0 方案、Proma 参考材料 | 是，但只改 Project_R 自有文档 | 更新需求、阶段进度、下一步计划、验收记录 |
| `docs/` | 项目维护说明、测试说明、Agent 设计规范 | 是 | 写维护手册、测试清单、故障排查、操作说明 |
| `backend/prompt_presets/` | 后端强制注入或预留的提示词文件 | 是，尤其是 `global-base-prompt.md` | 填写公司全局底层规则、统一业务背景、回答边界 |
| `backend/skills/` | Project_R 后端业务 Skill | 是，但建议一次只改一个 Skill | 新增/修改业务 Skill、输出格式、字段要求 |
| `.agents/skills/` | Codex/Agent 本地工作技能说明 | 是，偏开发协作 | 修改 Agent 如何分析、提问、写方案、生成文档 |
| `.claude/skills/` | 历史 Claude 系 Agent 本地技能说明 | 不再主动维护 | 仅在仍使用 Claude Code 时参考 |
| `backend/templates/` | 后端文件生成模板 | 是 | 放公司 Word/Excel/PPT 模板，后续接入正式模板渲染 |
| `backend/workspace_data/global/company-wiki/` | GBrain 公司知识库资料区 | 是，按 raw/derived/manifests 分层维护 | 放入 raw 原始资料、审核 derived 派生 Markdown、查看 manifest |
| `backend/workspace_data/` | 工作区/项目资料真实存储目录 | 可以通过软件上传维护，不建议直接手改 | 项目合同、报价、会议纪要、图纸资料等 |

## 后端功能目录

| 路径 | 作用 | 修改风险 | 说明 |
|---|---|---|---|
| `backend/api/` | HTTP 接口层 | 中高 | 聊天、登录、工作区、文件、管理员、RAG、Skill 等接口入口 |
| `backend/api/workspaces.py` | 工作区与项目文件管理 | 中高 | 多文件上传、100MB 限制、回收区、权限、审计、项目索引刷新入口 |
| `backend/api/chat.py` | 聊天发送、附件、GBrain/项目资料注入 | 高 | system prompt 组合、Global Base Prompt、项目资料作用域、LLM 调用 |
| `backend/api/skills.py` | Skill API | 中 | Skill 列表、匹配、启动、补参、查看运行状态 |
| `backend/api/admin.py` | 管理员 API | 中 | 用户管理、审计日志、知识审核等管理员能力 |
| `backend/core/` | 核心业务逻辑 | 高 | LLM、GBrain adapter、资料提炼、Skill 执行、文件渲染、意图识别 |
| `backend/core/gbrain.py` | GBrain 服务与查询 adapter | 高 | service health、source 状态、query/sync/doctor、启动/重启 |
| `backend/core/gbrain_ingest.py` | raw 到 derived 的导入编译 | 高 | Markdown/DOCX/PDF pending_review、manifest、本地 Git |
| `backend/core/llm.py` | LLM Provider 抽象 | 高 | Claude/OpenAI-compatible/DeepSeek、多 Key 轮询、失败降级 |
| `backend/core/skill_runner.py` | Skill 加载与匹配 | 高 | 读取 Skill 元数据、匹配触发、启动运行 |
| `backend/core/skill_execution.py` | Skill 执行输出 | 高 | 补参完成后的执行、文件生成结果 |
| `backend/models/` | 数据库模型 | 高 | User、ChatSession、WorkspaceFile、AuditLog 等表结构 |
| `backend/tests/` | 后端单元测试 | 是，推荐经常补 | 每次改后端逻辑后补测试，尤其是权限、上传、RAG、Skill |
| `backend/main.py` | FastAPI 应用入口 | 高 | 路由注册、启动时初始化数据库 |
| `backend/requirements.txt` | Python 依赖声明 | 是，但要谨慎 | 新增 Office/PDF 解析库、RAG 库、文件处理库时必须写这里 |

## 前端功能目录

| 路径 | 作用 | 修改风险 | 说明 |
|---|---|---|---|
| `frontend/src/renderer/pages/` | 页面级组件 | 中高 | 主工作台、登录、欢迎、设置页 |
| `frontend/src/renderer/pages/AppPage.tsx` | 主聊天工作台 | 高 | 会话列表、消息区、输入区、模式切换、工作区入口 |
| `frontend/src/renderer/components/` | 可复用组件 | 中 | 设置弹窗、工作区文件面板、标签栏、搜索弹窗、图标等 |
| `frontend/src/renderer/components/WorkspaceFilePanel.tsx` | 项目文件面板 | 中高 | 上传、拖拽、回收区、恢复、永久删除、刷新项目索引按钮 |
| `frontend/src/renderer/components/SettingsModal.tsx` | 设置弹窗 | 高 | 通用设置、提示词、管理员后台、服务器连接 |
| `frontend/src/renderer/api/` | 前端请求封装 | 中高 | 与后端接口路径和返回类型对应 |
| `frontend/src/renderer/api/workspaces.ts` | 工作区 API 封装 | 中 | 上传、删除、恢复、刷新索引等前端调用入口 |
| `frontend/src/renderer/api/types.ts` | API 类型定义 | 中 | 后端响应结构变更后要同步更新 |
| `frontend/src/renderer/atoms/` | Jotai 状态 | 中 | 登录、服务器地址、会话、工作区、标签页状态 |
| `frontend/src/renderer/styles.css` | 全局样式 | 中 | UI 视觉、排版、响应式、组件样式 |
| `frontend/src/main/` | Electron 主进程 | 高 | 窗口、preload、用户本机提示词文件、窗口状态 |

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
| `frontend/dist/` | 前端构建产物 | 不手改；由 `npm run build` 生成 |
| `backend/workspace_data/global/company-wiki/` | GBrain 公司知识库运行资料 | raw 可手动投喂；derived 通过审核流程维护 |
| `backend/generated_files/` | AI 生成的下载文件 | 不手改；由文件生成接口和清理逻辑管理 |
| `backend/session_attachments/` | 会话临时附件 | 不手改；删除会话时应自动清理 |
| `backend/workspace_data/*/.trash/` | 工作区回收区 | 优先通过软件恢复/永久删除 |
| `app.db`、`backend/app.db` | SQLite 数据库 | 不直接编辑；用 API 或迁移逻辑修改 |

## 常见任务该从哪里开始

| 任务 | 先看哪里 | 验证方式 |
|---|---|---|
| 改上传文件大小限制 | `backend/api/workspaces.py`、`WorkspaceFilePanel.tsx` | `backend/tests/test_workspace_files.py` + 前端 build |
| 改工作区文件权限 | `backend/api/workspaces.py` | 后端 workspace tests |
| 改回收区逻辑 | `backend/api/workspaces.py`、`WorkspaceFilePanel.tsx` | 上传、删除、恢复、永久删除手工验收 |
| 让 Word/PDF/Excel 可被项目问答引用 | 新增解析模块到 `backend/core/`，接 GBrain 项目 source 或 `backend/api/workspaces.py` | 新增解析测试 + 项目对话验收 |
| 改 Global Base Prompt | `backend/prompt_presets/global-base-prompt.md` | 发普通聊天、项目聊天、Skill 触发检查是否生效 |
| 改聊天消息排版 | `frontend/src/renderer/pages/AppPage.tsx`、`styles.css` | `npm run build` + Electron 手工看界面 |
| 改设置页 | `SettingsModal.tsx`、`styles.css` | `npm run build` + 登录管理员/普通用户检查 |
| 新增业务 Skill | `backend/skills/`、`docs/agents/skills-design.md` | Skill 列表、匹配、启动、补参、输出文件测试 |
| 更新开发进度 | `references/Project_R 开发流程.md` | 勾选必须对应已验证功能 |
| 更新产品范围 | `references/Project_R PRD.md` | 保持与开发流程一致 |
| 更新 Agent 工作规则 | `AGENTS.md` | 当前只维护 AGENTS.md |

## 修改前后建议流程

1. 先在本文件定位功能归属。
2. 读对应 PRD / 开发流程段落，确认当前阶段是否允许改。
3. 修改最小相关文件，不顺手重构无关代码。
4. 后端改动跑：`cd backend && .\venv\Scripts\python.exe -m unittest discover -s tests`
5. 前端改动跑：`cd frontend && npm run build`
6. 涉及 UI、上传、文件下载、RAG 引用时，再做 Electron 手工验收。
7. 验证通过后，同步更新 `references/Project_R 开发流程.md`。
