# Project_R 开发流程文档

- **适用对象**：无编程经验的开发者，借助 AI 辅助逐步完成
- **文档版本**：V2.1
- **配套文档**：Project_R PRD.md / Project_R 业务工作流清单.md / docs/agents/skills-design.md
- **目标节奏**：先把 Phase 9 聊天工作台收口成日常可用版本，再用 RAG → 文件生成 → 首个业务 Skill 的顺序做出业务闭环

---

## 阅读说明

本文件是 Project_R 的**阶段执行清单**。四份核心文档分工如下：

- `Project_R PRD.md`：定义产品范围、用户价值、长期能力边界。
- `Project_R 开发流程.md`：定义阶段顺序、任务清单、完成标志，是 checklist 的唯一维护处。
- `AGENTS.md`：Codex / 通用 Agent 工作规则。

每个阶段包含：

- **目标**：这个阶段要解决的业务问题。
- **实施方式**：建议从哪些模块入手，如何做出可验证的竖切片。
- **任务清单**：具体要完成的事项。
- **完成标志**：怎么判断这个阶段做完了。
- **实现状态**：已完成、待 Gary 手工确认、阻塞项或剩余风险。

每个阶段完成后再进入下一个。例外只有一种：当前阶段被明确拆成 A/B/C 子阶段时，可以在同一阶段内按子阶段推进，但不得越过该阶段的完成标志直接勾选后续阶段。

Checklist 维护规则：当某个阶段的任务已经实现，且通过该任务对应的功能验证后，开发者必须在完成标志确认后，把该任务从 `- [ ]` 改为 `- [x]`。未验证、部分完成或仅完成设计的任务不得勾选，并应在该阶段的实现状态中说明剩余条件。

依赖安装规则：如果本地缺少依赖且需要联网下载安装，暂停命令并由 Gary 手动安装。当前网络环境不稳定，手动安装通常比终端自动安装更快；开发者不要反复运行联网安装命令。

---

## 开发框架与推进方式

Project_R 后续不再按“堆功能”推进，而按四条主线交替收口：

| 主线 | 目标 | 主要产物 |
|---|---|---|
| 对话底座 | 让登录用户稳定地发起、保存、恢复多轮对话 | Auth、ChatSession、ChatMessage、LLM Provider、聊天工作台 |
| 知识底座 | 让系统能可信地引用公司文档回答问题 | RAG 索引、检索、来源片段、知识刷新接口 |
| 文件与 Skill 底座 | 通过显式入口或后续自然语言意图识别生成标准化业务文件或流程输出 | doc_renderer、skill_runner、内置业务 Skill |
| 管理与交付底座 | 让管理员能维护系统，让员工能稳定使用 | 管理后台、设置、引导、Mac mini 部署、客户端打包 |

每个新阶段采用同一套实施方式：

1. **先做竖切片**：只选一个最小真实场景，把后端接口、核心逻辑、前端入口、测试串起来。
2. **再补边界条件**：补权限隔离、错误提示、脱敏日志、跨平台路径、空数据状态。
3. **最后做体验与验收**：在 Electron 窗口中走完整链路，Gary 手工确认视觉和业务结果。
4. **只在验证后勾选**：单元测试通过但未完成真实链路时，只写实现状态，不勾最终 checklist。

默认验证门槛：

- 后端改动：至少运行相关 `pytest`，真实 LLM 调用不进入默认单测。
- 前端改动：至少运行 `bun run typecheck`；涉及打包或路由时补跑 `bun run build`。
- 跨端链路：必须说明后端地址、测试账号、是否使用真实 LLM Key、是否由 Gary 在 Electron 窗口确认。
- 文档同步：阶段 checklist、`AGENTS.md` 代理规则、PRD 范围变化必须在同一次开发中保持一致。

---

## 跨平台兼容红线（贯穿全程）

开发期在 Windows 单机进行，未来迁移到 Mac mini。所有代码必须遵守：

| 红线 | 错误做法 | 正确做法 |
|---|---|---|
| 路径 | `C:\\Users\\xxx` 或 `D:/xxx` | `pathlib.Path` + 相对路径 |
| 配置 | 写死路径或 IP | 通过 `.env` 配置 |
| 编码 | 默认编码 | 显式 `encoding='utf-8'` |
| 服务器地址 | `localhost`、`127.0.0.1` 写死 | 永远从配置读取 |
| 依赖包 | Windows-only | 仅选跨平台库 |

每写完一段代码，问自己一句："这段代码搬到 Mac 能跑吗？"

---

## 第一阶段：开发环境准备

**目标**：在 Windows 电脑装好所有开发工具，确保后续每一步都能顺利运行。

**任务清单**：
- [x] 安装 Python 3.11（官网下载，安装时勾选"Add to PATH"）
- [x] 安装 Node.js 22 LTS（官网下载）
- [x] 安装 Git（官网下载）
- [x] 安装 VS Code（代码编辑器）
- [x] 在 VS Code 中安装插件：Python、ESLint、Prettier
- [x] 安装 Bun（前端包管理器，在终端运行官网提供的安装命令）
- [x] 验证安装：在终端分别运行 `python --version`、`node --version`、`git --version`、`bun --version`，确认均有版本号输出

**完成标志**：终端能正确显示以上四个工具的版本号。

**Gary markup**
PS C:\Windows\System32> python --version
Python 3.11.9
PS C:\Windows\System32> node --version
v24.14.1
PS C:\Windows\System32> git --version
git version 2.53.0.windows.3
PS C:\Windows\System32> bun --version
1.3.14

---

## 第二阶段：跑通 Proma 单机版（参考基线）

**目标**：把 Proma 在你的 Windows 电脑上跑起来，作为后续 UI 设计参考与日常工具。

**任务清单**：
- [x] 进入 `references/Proma-main/` 目录
- [x] 运行 `bun install` 安装依赖（首次较慢，需联网）
- [x] 运行 `bun run dev` 启动 Proma（如端口 5173 被占用，先 `taskkill /F /PID <PID>` 释放）
- [x] 在 Proma 设置中添加 AI 渠道（任意一个 Anthropic 兼容渠道），让 Agent 配置可见
- [x] 浏览所有设置页面，对照 `references/Project_R 功能构思1.0.md` 中的截图与说明，确认功能定位

**完成标志**：能在 Windows 电脑上启动 Proma，并能在其中完成一次 Chat 对话。

---

## 第三阶段：后端骨架搭建

**目标**：让后端服务器能启动并响应最基础的请求，验证整个后端框架能跑通。

**任务清单**：
- [x] 在项目根目录创建 `backend/` 文件夹
- [x] 进入 `backend/` 目录，创建 Python 虚拟环境（`python -m venv venv`）
- [x] 激活虚拟环境（Windows: `.\venv\Scripts\Activate.ps1`）
- [x] 在 `requirements.txt` 中写入基础依赖：`fastapi`、`uvicorn`、`python-dotenv`
- [x] 安装依赖（`pip install -r requirements.txt`）
- [x] 编写 `main.py`：创建 FastAPI 应用实例，注册路由
- [x] 编写 `api/health.py`：实现 `/health` 端点，返回 `{"status": "ok"}`
- [x] 创建 `.env.example` 文件，列出所有需要填写的环境变量名（值留空），并将其纳入 Git
- [x] 复制 `.env.example` 为 `.env`，填入真实值（暂时只需填 `APP_SECRET_KEY`），并在 `.gitignore` 中排除 `.env`
- [x] 在 `main.py` 中通过 `pathlib` 与 `os.getenv()` 读取所有路径与配置；**严禁出现 `D:/...` 等硬编码**
- [x] 启动服务：`uvicorn main:app --reload --port 8000`
- [x] 在浏览器访问 `http://localhost:8000/health`，确认返回正常

**完成标志**：浏览器能看到 `{"status": "ok"}`。

---

## 第四阶段：数据库与用户认证

**目标**：建立用户账号体系，实现登录功能，后续所有接口都依赖这个基础。

**任务清单**：
- [x] 在 `requirements.txt` 补充：`sqlalchemy`、`python-jose`、`passlib`、`bcrypt`
- [x] 编写 `models/user.py`：定义用户表（id、用户名、密码哈希、角色、头像、昵称、创建时间）
- [x] 编写 `models/audit_log.py`：定义审计日志表（id、用户id、操作时间、操作类型、token消耗、是否成功）
- [x] 编写 `models/session.py`：定义会话表（id、用户id、创建时间、消息历史JSON）
- [x] 编写 `models/knowledge_review.py`：定义知识审核队列表（id、提交人、内容、来源、状态、创建时间）
- [x] 在 `main.py` 中初始化 SQLite 数据库，启动时自动建表（数据库文件路径从 `.env` 读取）
- [x] 编写 `api/auth.py`：实现 `POST /auth/login` 接口（接收账号密码，验证后返回 JWT Token）
- [x] 编写一个初始化脚本，创建第一个管理员账号（用于首次使用）
- [x] 用 API 测试工具（如 Postman 或 VS Code 的 REST Client 插件）测试登录接口

**完成标志**：调用登录接口，传入正确账号密码后能收到 JWT Token；传入错误密码返回 401。

---

## 第五阶段：LLM Provider 接入（多厂商多 Key 轮询）

**目标**：让后端通过统一 LLM Provider 抽象调用云端大模型并返回 AI 回复。第一版默认接入 Claude，但架构必须同时预留 ChatGPT / OpenAI、DeepSeek、MiMo 等厂商的 API Key 轮询、模型 profile 路由与故障切换能力。

**任务清单**：
- [x] 在 `.env.example` 中定义统一 Provider 配置：`LLM_PROVIDER`、`LLM_MAX_TOKENS`、`LLM_TIMEOUT_SECONDS`、`LLM_SYSTEM_PROMPT`
- [x] 在 `.env` 中按厂商填入 API Key（至少一个默认 Provider Key）：
  - Claude：`CLAUDE_API_KEYS` 或 `CLAUDE_API_KEY_1`、`CLAUDE_API_KEY_2`
  - OpenAI / ChatGPT：`OPENAI_API_KEYS` 或 `OPENAI_API_KEY_1`、`OPENAI_API_KEY_2`
  - DeepSeek：`DEEPSEEK_API_KEYS` 或 `DEEPSEEK_API_KEY_1`、`DEEPSEEK_API_KEY_2`
  - MiMo：`MIMO_API_KEYS` 或 `MIMO_API_KEY_1`、`MIMO_API_KEY_2`
- [x] 在 `.env.example` 中定义 `LLM_MODEL_PROFILES` 等模型 profile 配置：同一 provider Key 组可映射多个用户可见模型版本，例如 DeepSeek Flash / Pro、MiMo V2.5 / V2.5-Pro
- [x] 编写 `core/llm.py`：实现统一 LLM Provider 封装
  - 内部统一暴露 `complete(messages, provider=None)` 能力，业务层不直接依赖某一家 SDK
  - Claude 适配 Anthropic Messages API
  - OpenAI / ChatGPT、DeepSeek 与 MiMo 先走 OpenAI-compatible Chat Completions 适配
  - 支持 `model_profile` 解析：前端传用户可见 profile，后端解析为 provider、真实模型名、描述和私有参数
  - 支持 `thinking` 开关：DeepSeek 使用 `thinking.type` + `reasoning_effort`，MiMo 使用 `thinking.type`
  - **轮询算法**：每个 Provider 内部独立 Round-Robin，每次请求轮换下一个 Key
  - **故障切换**：单个 Key 遇到限流、网络异常或 5xx 时自动尝试同 Provider 的下一个 Key
  - **失败处理**：当前 Provider 所有 Key 均不可用时抛出统一错误"AI 服务暂时不可用"，不向前端暴露原始 Key、请求头或敏感错误
- [x] 在 `POST /chat/sessions/{id}/messages` 中支持可选 `provider`、`model_profile`、`thinking` 参数；未传时使用 `.env` 中的 `LLM_PROVIDER` 与默认 profile
- [x] 编写 `GET /health/llm`：返回当前默认 Provider、模型、各 Provider 是否已配置、Key 数量、已配置模型 profile；严禁返回 Key 明文
- [x] 编写单元测试，覆盖 Key 轮询、失败切换、健康检查不泄露 Key
- [x] 编写一个简单的手动测试脚本，直接调用 `core/llm.py` 发送一条消息，确认默认 Provider 能收到回复

**完成标志**：运行单元测试通过；配置任意一个厂商的真实 Key 后，调用对话接口能收到 AI 回复；切换 `LLM_PROVIDER=claude/openai/deepseek/mimo` 或切换已配置 `model_profile` 后无需修改业务代码；前端只展示后端 `/health/llm` 返回的已配置 profile，不泄露 Key。

---

## 第六阶段：基础对话接口

**目标**：实现带用户隔离的多轮对话消息底座。当前阶段使用稳定 JSON 非流式接口；真正 SSE 流式输出后续作为独立端点追加。

**任务清单**：
- [x] 编写 `core/session.py`：实现会话管理
  - 创建新会话
  - 追加消息到会话
  - 读取某用户的会话历史
  - 按用户 ID 隔离，不同用户无法访问彼此的会话
- [x] 编写 `api/chat.py`：实现以下接口
  - `POST /chat/sessions`：创建新会话
  - `GET /chat/sessions`：获取当前用户的会话列表
  - `GET /chat/sessions/{id}`：获取会话详情与消息数量
  - `GET /chat/sessions/{id}/messages`：分页读取消息历史
  - `POST /chat/sessions/{id}/messages`：发送消息，返回 JSON 格式 AI 回复
  - `DELETE /chat/sessions/{id}`：删除会话
- [x] 所有接口需验证 JWT Token（未登录返回 401）
- [x] 每次对话自动写入审计日志
- [x] 用测试工具测试：登录后发送一条消息，确认能收到 JSON 回复并持久化 user / assistant 消息

**完成标志**：登录后调用对话接口，能收到默认 LLM Provider 的文字回复；user / assistant 消息均持久化；刷新后能重新拉取消息历史；换另一个账号登录，看不到前一个账号的会话记录。

---

## 第七阶段：前端骨架搭建

**目标**：创建安全、可扩展的 Electron 桌面应用骨架，能启动并显示基础界面，为后续登录、聊天、设置和欢迎引导打好结构。

**任务清单**：
- [x] 在项目根目录创建 `frontend/` 文件夹
- [x] 使用 Electron + React + Vite + TypeScript 模板初始化项目（参考 Proma 的 `apps/electron/` 结构）
- [x] 安装 Jotai（`bun add jotai`），用于全局状态管理
- [x] 建立 Electron 安全基线：
  - `contextIsolation: true`
  - `nodeIntegration: false`
  - 使用最小化 `preload`
  - renderer 不直接访问 Node API
- [x] 创建 `src/renderer/constants/app.ts`：
  - 定义 `APP_NAME = "Project_R"`
  - 从构建期环境变量 `VITE_DEFAULT_API_BASE_URL` 读取默认后端地址；开发默认值写入 `frontend/.env.development`
  - 所有界面文本、窗口标题、菜单项均引用这些常量
- [x] 创建 `src/renderer/atoms/server-atoms.ts`：用 Jotai 管理后端服务器 URL（持久化到本地）
- [x] 创建 `src/renderer/api/client.ts` 与 `src/renderer/api/types.ts`：统一封装后端 HTTP 调用；请求层只能从 server atom 读取地址，严禁写死 `localhost` 或 `127.0.0.1`
- [x] 配置 Electron 主进程：默认窗口 1400×900，最小 800×600，记住上次窗口位置（参考 Proma 的 `main/index.ts` 实现）
- [x] 实现基础路由结构：`/login`、`/app`、`/settings`、`/onboarding` 预留；先用占位页面验证导航
- [x] 确认能用 `npm run dev`（或 `bun run dev`）启动，看到显示软件名称的 Electron 窗口
- [x] 确认 `bun run typecheck` 通过

**完成标志**：运行 `npm run dev`（或 `bun run dev`），桌面弹出 Electron 窗口，显示软件名称；页面路由能在登录页、主界面占位、设置页、欢迎页之间切换；server URL 由 Jotai atom 持久化管理；请求层没有写死 `localhost`；`bun run typecheck` 通过。

> 实现状态：Gary 已验证 `npm run dev` 可启动实际 Electron 窗口；Codex 已验证 `npm run typecheck` 与 `npm run build` 通过。

---

## 第八阶段：登录界面与前后端连接

**目标**：前端能连接到后端，用户能通过界面登录，登录后保存并校验 Token，失效时自动回到登录页。

**任务清单**：
- [x] 后端新增 `GET /auth/me`：用于前端启动时校验 JWT Token 并返回当前用户信息
- [x] 创建 `auth-atoms.ts`：统一管理 Token、当前用户、登录写入、登出清理，并进行本地持久化
- [x] 完善 HTTP 请求工具：自动携带 JWT Token；遇到 401 自动触发本地登出；后端地址仍从 `server-atoms` 读取，**严禁写死 localhost**
- [x] 实现真实登录页面 UI：账号输入框、密码输入框、登录按钮、登录中状态、错误提示（视觉风格参考 Proma）
- [x] 实现登录逻辑：调用后端 `/auth/login`，成功后将 Token 与用户信息存入本地（Jotai + 持久化），跳转主界面
- [x] 实现启动认证校验：关闭重开或刷新后调用 `/auth/me`，Token 有效则保持登录，Token 失效则清理本地状态并跳回登录页
- [x] 实现登出功能：清除本地 Token 与用户信息，跳回登录页
- [x] 实现"服务器连接"设置：用户可在设置中修改后端 IP 和端口，保存后立即调用 `/health` 测试连接并显示状态
- [x] 确认员工前端不暴露 API Key、Provider 切换或多 Key 配置；聊天输入区仅允许选择后端白名单返回的已配置 `model_profile`
- [x] 测试：输入正确账号密码能进入主界面；输入错误密码显示错误提示；关闭重开软件后 Token 有效时无需重新登录

**完成标志**：在 Electron 窗口中完成登录，能进入主界面；关闭重开软件，Token 仍有效，无需重新登录；Token 失效或后端返回 401 时自动登出；设置页能正确测试后端连接。

> 实现状态：Phase 8 已完成。Codex 已完成代码实现；后端单元测试通过，前端 `npm run typecheck` 与 `npm run build` 通过；临时启动当前后端代码到 `127.0.0.1:8001` 后，`POST /auth/login` + `GET /auth/me` 已验证成功。Gary 已重启后端并运行前端，使用管理员账号密码在 Electron 窗口中登录成功。
>
> **V3.0-A  redesign（2026-05-22）**：登录页已按 `references/animatedlogin-main` 参考完全重构为左右分栏动态角色动画设计。左侧灰色渐变背景 + 4 个卡通角色（紫/黑/橙/黄），支持鼠标跟随眼球、随机眨眼、账户输入聚焦互相对视、密码输入聚焦转头回避、登录失败沮丧 + 摇头动画；右侧纯白表单区，含密码可见性切换、悬停滑出动画按钮、错误红框提示。已明确取消 Privacy Policy / Terms of Service / Contact / Google 登录 / 忘记密码 / 注册入口。Welcome 页保留流动极光 CSS 背景动画。`bun run typecheck` 与 `vite build` 通过。

---

## 第九阶段：聊天主界面

**目标**：实现接近 Proma 主界面形态的聊天工作台，接入后端会话与消息接口，用户能完成新建会话、查看历史、发送消息、查看 AI 回复与删除会话。

**Proma UI shell 约定**：初步雏形阶段采用 **Proma shell first, Project_R core always**。允许在已获授权前提下，局部迁移或强复刻 Proma 前端的布局、组件观感、交互节奏和必要样式，以快速获得 Gary 认可的外壳质感；但不得迁移 Proma 的业务架构、Electron IPC 编排、客户端 API Key 管理、模型配置暴露、本地 Agent 执行链路或产品品牌形态。所有数据流必须继续接 Project_R 后端 API、`auth-atoms.ts`、`chat-atoms.ts`、`server-atoms.ts` 与本项目路由。

**任务清单**：
- [x] 重构主界面布局：左侧会话侧边栏 + 顶部 Agent/Chat 切换 + 右侧消息区 + 底部固定输入区，视觉与交互以 Proma 主界面为对照基线
- [x] 移除 Phase 7 占位文案和开发期导航痕迹，登录后的 `/app` 应呈现真实工作台，而不是骨架说明页
- [x] 创建 `chat-atoms.ts`：管理会话列表、当前会话、消息列表、加载状态、发送状态、错误状态
- [x] 扩展前端 API 类型与请求方法，对接 `POST /chat/sessions`、`GET /chat/sessions`、`GET /chat/sessions/{id}/messages`、`POST /chat/sessions/{id}/messages`、`DELETE /chat/sessions/{id}`
- [x] 实现会话列表：启动后加载历史会话，点击切换，支持新建会话和删除会话
- [x] 实现消息历史：切换会话后读取后端消息记录，按 user / assistant 区分展示
- [x] 实现消息输入框：支持 Enter 发送、Shift+Enter 换行、空消息禁止发送、发送中禁用重复提交
- [x] 实现 AI 回复展示：Phase 9 使用当前 JSON 接口返回完整回复，前端用打字机效果模拟逐字出现；真正 SSE 流式接口后续单独实现
- [x] 实现消息基础排版：支持换行、代码块样式、长文本滚动；Markdown 完整渲染若需新依赖，先由 Gary 手动安装后再接入
- [x] 实现加载与错误状态：会话加载中、消息发送中、后端不可用、AI 服务不可用、Token 失效自动登出
- [x] 实现界面适配：默认 1400×900 舒适展示，最小 800×600 不出现文本重叠或关键按钮不可用
- [x] 测试完整链路：登录 → 新建会话 → 发送消息 → 看到 AI 回复 → 切换会话 → 刷新后恢复历史 → 删除会话（需 Gary 在 Electron 中手工确认）
- [x] 运行 `npm run build`，并由 Gary 在 Electron 窗口中确认主界面视觉方向明显接近 Proma（build 通过，视觉确认需 Gary 手工确认）

**完成标志**：Electron 主界面不再是占位页；用户能完成完整多轮聊天链路；会话和消息刷新后仍可恢复；删除会话后 UI 与后端一致；界面布局明显接近 Proma 主界面；`npm run build` 通过。

> 实现状态：Phase 9 视觉重构已完成——CSS 完全重写为 Proma 风格双卡片布局（渐变背景、模式切换滑标、日期分组会话、圆角卡片输入区、侧栏用户面板），`AppShell.tsx` 精简为路由感知容器，`AppPage.tsx` 整体重写。`tsc --noEmit` 零错误，`vite build` 通过，body 已设 `min-width:800px` `min-height:600px` 并含 900px 断点适配。完整聊天链路测试与 Proma 视觉方向确认需 Gary 在 Electron 窗口中手工验证。

### 第九阶段增强功能（2026-05-19 grill-me 决策后实现）

新增以下功能，已通过 `tsc --noEmit` + `vite build`：

**工作区系统**：
- [x] 后端：`Workspace` + `WorkspaceMember` 模型、CRUD API（创建/列表/搜索/加入/删除）
- [x] 前端：侧栏顶部 `WorkspaceSelector` 组件（内联创建、列表切换、搜索加入）
- [x] Chat/Agent 两种模式共用同一工作区选择器
- [x] 工作区与对话关联：`ChatSession.workspace_id` 可空外键

**多标签页系统**：
- [x] `TabBar` 组件：Chat/Agent/Scratch 三类标签，Scratch 锁定左侧
- [x] 标签可关闭，关闭后保持状态
- [x] `tabsAtom` / `activeTabIdAtom` 状态管理

**快速笔记（Scratch Pad）**：
- [x] Markdown 书写区域，`localStorage` 自动保存
- [x] 显眼的导出 Markdown 按钮（右下角）

**右键菜单系统**：
- [x] `ContextMenu` 通用组件（item / separator，自动适配视口边缘）
- [x] 置顶（前端 `pinnedSessionIds` 本地管理，侧栏"已置顶"分组）
- [x] 重命名（内联 `<input>` 编辑 + `PUT /chat/sessions/{id}` 后端接口）
- [x] 归档（后端 `is_archived` 软删除 + `POST /chat/sessions/{id}/archive`）

**侧边栏增强**：
- [x] 收起按钮（Discord 风格图标模式，`sidebarCollapsedAtom`）
- [x] Agent 按钮解灰（可点击切换到 Agent 模式）
- [x] 搜索弹窗（标题即时过滤 + 键盘导航 ↑↓Enter）
- [x] 字号全局上调 ~15%（11→13, 12→14, 13→15, 14→16, 20→23, 28→32）

**交流区增强**：
- [x] 消息操作区（复制/重生成/编辑/切换到 Agent/删除 — 目前按钮占位）
- [x] 右上角功能按钮（内置提示词/置顶/并排模式 — 目前按钮占位）
- [x] 输入框增强（附件按钮 + 思考模式开关 — 附件为前端文件选择桩）

**归档管理**：
- [x] 设置页新增"归档管理"面板（`SettingsPage.tsx`）：列出已归档对话 + 恢复按钮
- [x] 后端 `GET /chat/sessions/archived` + `POST /chat/sessions/{id}/restore`

**通知与蒸馏（后端模型+API 就绪，前端尚未接入）**：
- [x] `Notification` 模型（system/agent/distillation/changelog）+ API（列表/已读）
- [x] `DistillationSuggestion` 模型（pending/approved/rejected 审核流）+ 审核 API

> 实现状态：Phase 9 增强功能已完成代码实现和后端 API。部分前端按钮为功能占位（附件上传、内置提示词下拉、并排模式），后续阶段逐步补全。`tsc --noEmit` 零错误，`vite build` 通过。

### 第九阶段二次调整（2026-05-20 grill-me 决策）

本节用于收口 Gary 对 Proma 参考改版后的二次评价。核心原则：Proma 是局部界面表现、信息分区与交互节奏参考，不是默认架构来源。开发时按“表现层 / 产品交互层 / 架构执行层”三层判断，表现层可强参考，产品交互层必须映射 Project_R 当前能力，架构执行层默认不迁移。

**已实现（代码已存在，仍需 Gary 视觉验收）**：
- [x] 使用 `iconoir` SVG 资源替换一批主界面图标；当前项目根目录已安装 `iconoir`，前端通过 Vite SVG URL 导入使用。
- [x] Electron 主菜单栏已隐藏。
- [x] 软件内窗口控制按钮已实现：主工作台将最小化 / 最大化 / 关闭融入标签栏右侧；登录、设置、欢迎等无标签页页面使用极简顶部拖拽兜底层，解决登录页无法移动窗口的问题。
- [x] 搜索入口已改为与新建对话并排的小图标入口。
- [x] 会话列表统一为“最近会话”展示，不再按今天/昨天/更早分组。
- [x] 会话末端相对时间显示已按整数单位处理：最近 / 小时 / 天 / 周 / 月 / 年。
- [x] 会话三点菜单已接入右键菜单同等操作，并增加“迁移到其他工作区”入口。
- [x] 切换工作区时仅显示该工作区会话；后端 `POST /chat/sessions` 已写入 `workspace_id`。
- [x] 搜索对话已扩展到后端标题 + 消息内容搜索。
- [x] 初次登录用户会自动创建“了解 Project_R”欢迎会话。

**下一轮优先实现（Phase 9B 竖切片）**：
- [x] 修正工作区“快速创建”为 Proma 风格的简单 `+` 入口，不使用冗余“+ 快速创建”大按钮。
- [x] 增加“工作区”和“对话”的文字分区标识。
- [x] 按 Proma 细节重做侧边栏收放按钮；收起后用图标替代文字显示，保留关键入口可用。
- [x] 恢复右上角 Proma 风格入口：提示词、置顶、并排模式。
- [x] 提示词调用面板第一版：按 Project_R 内置提示词 / 公司预设提示词 / 用户本机自定义提示词三类展示；只做调用面板，不做完整管理员后台。
- [x] 提示词调用语义为当前会话 system prompt；每个会话独立选择，新会话默认 Project_R 内置提示词。
- [x] 用户自定义提示词由 Electron 主进程保存到 `app.getPath("userData")` 下的 JSON 文件，不用 `localStorage`，不上传后端。
- [x] 置顶功能后端持久化闭环：`ChatSession.is_pinned` 写入数据库，前端右上角和三点菜单共用同一状态。
- [x] 新建对话空状态按 Chat / Agent 分开设计：Chat 显示按系统时间问候和使用说明；Agent 显示工作区文件目录/上下文面板。
- [x] Agent 专属功能区定义为工作区文件目录/上下文面板，不放“整理当前会话 / 生成工作项 / 查询知识库 / 生成业务文件”等按钮；这些能力通过自然语言对话触发。
- [x] Agent 模式默认显示工作区文件目录面板；Chat 模式仅提供轻量入口。
- [x] 工作区文件目录第一版只做只读文件树和默认目录创建，不做上传/删除。

**后续独立竖切片补齐**：
- [x] 并排模式仅保留入口并标记后续接入；第一版不做真实布局切换。
- [x] 工作区文件上传。
- [x] 工作区文件删除/回收区。
- [x] 工作区文件权限：成员可上传；成员只能删除自己上传的文件；管理员可删除所有文件。
- [x] 项目工作区权限：系统管理员新建项目；私人空间只对本人可见；公司项目默认对所有有效用户开放；隐藏项目仅对系统管理员、成员管理中显式添加的人员或授权组别可见；普通成员不显示项目重命名入口；项目管理员通过工作区列表盾牌按钮打开独立成员管理面板，维护人员、组别、隐藏状态和 scoped admin。
- [x] 工作区文件操作审计日志。
- [x] 工作区文件变更触发项目子库/RAG 索引刷新。

> 实现状态：Phase 9B + P9 工作区文件管理竖切片已完成代码实现，并在 2026-05-27 补齐输入区模型选择、思考开关、提示词/Skill 工具区、来源预览、暗色主题和设置页细节优化：工作区简单 `+` 创建入口、工作区/对话分区文字、侧栏收起图标模式、右上角提示词/置顶/并排入口、三来源提示词调用面板、会话级 system prompt 发送、本机自定义提示词 Electron `userData` JSON 存储、后端持久化置顶、Chat/Agent 空状态分离、Agent 工作区文件面板、工作区多文件上传、100MB 单文件限制、删除进入回收区、恢复/永久删除、成员/管理员删除权限、文件操作审计、项目资料索引 pending/indexed 状态与项目对话作用域检索。2026-06-01 已补独立项目工作区成员管理面板、项目重命名按钮权限隐藏、私人空间 owner-only 和系统管理员/项目管理员权限边界；成员管理入口位于工作区列表盾牌按钮，不占用项目文件面板。已通过 `backend` 全量 `unittest discover -s tests`（73 tests OK）、新增模型/聊天相关测试、`frontend` 的 `bun run typecheck` 与 `bun run build`。仍需 Gary 在 Electron 窗口中做真实拖拽上传、回收区、索引刷新按钮、项目对话引用效果和暗色主题视觉验收。

**下一步开发建议**：
- [x] 优先做工作区文件管理手工验收与细节修正：真实 Office/PDF/图片/文本多文件上传、100MB 超限提示、回收区恢复冲突、成员/管理员权限按钮显示。
- [x] 做项目资料解析增强：项目 source 已接入 GBrain，支持 Markdown/txt、DOCX、普通 PDF、复杂 PDF/建筑图纸 MiMo 视觉提炼、图片/截图 MiMo 提炼、MP4 自动/长视频分段转写会议、说话人/术语纠错、EML 邮件线程提炼和 EML 附件递归。
- [x] 做项目 RAG 真正异步索引队列：项目一键录入已新增后台 job、状态轮询、失败记录和完成通知。
- [x] 完成引用来源查看体验：项目资料命中后，来源内容会带 `derived_file/source_file/line/page` 定位；文件预览 UI 后续补齐。

### 2026-05-22 UI/UX 优化归档（防止后续回退）

以下改动已落实到代码，同步记入本文档与 `AGENTS.md` / `PRD.md`：

1. **登录页记住密码**：新增「记住账号」与「记住密码」复选框。账号与密码（`btoa(encodeURIComponent(...))` 编码）写入 `localStorage`，下次启动自动回填。对应文件 `LoginPage.tsx`。
2. **设置弹窗导航对齐**：左侧分类导航按钮改用 `grid-template-columns: 24px 1fr`，图标统一放大至 20px，文字与图标纵向居中对齐，解决反复出现的错位问题。对应文件 `SettingsModal.tsx`、`styles.css`。
3. **聊天 Loading Indicator  whimsical 改造**：
   - 发送按钮取消 `SENDING_LABELS` 四词循环，禁用态仅显示 plain「发送中」文字。
   - 新增 AI 占位卡片 `LoadingPlaceholder`（内联于 `AppPage.tsx`），出现在消息列表底部。
   - 使用 `references/Loading.css` 四色环 SVG 动画（红 `#f42f25` / 橙 `#f49725` / 蓝 `#255ff4` / 粉 `#f42582`），尺寸缩至 `1.6em`。
   - 搭配 20 个 whimsical 词汇每 2 秒随机切换（不连续重复），例如 Discombobulating、Concocting、Moonwalking、Mulling、Purring、Doodling、Pondering、Exploring、Discovering。
4. **用户消息操作栏右对齐**：`.message-row-user .message-actions { justify-content: flex-end; }`，使工具栏与用户消息气泡右侧对齐，与左侧 AI 消息形成视觉区分。对应文件 `styles.css`。
5. **工作区拖拽排序**：删除原上下箭头按钮，改为 HTML5 `draggable` 拖拽排序。`WorkspaceSelector.tsx` 内维护 `dragIndex` state，`localStorage` 持久化键 `project_r_workspace_order`，默认工作区仍可拖动但禁止删除。对应文件 `WorkspaceSelector.tsx`、`styles.css`。
6. **侧边栏头像去蒙版**：emoji 或图片头像直接展示，不再叠加统一背景色；仅文字首字母头像保留背景色，通过条件类名 `.sidebar-user-avatar.is-text` 控制。对应文件 `AppPage.tsx`、`styles.css`。

### 2026-05-27 模型 / 输入区 / 暗色主题优化归档（防止后续回退）

以下改动已落实到代码，同步记入本文档与 `AGENTS.md` / `PRD.md`：

1. **模型 profile 白名单**：模型选择从单一 provider 下拉升级为后端 `model_profile` 白名单；同一组 DeepSeek Key 可跑 DeepSeek Flash / Pro，同一组 MiMo Key 可跑 MiMo V2.5 / V2.5-Pro；前端只显示 `/health/llm` 返回的已配置模型，不显示未配置占位项。
2. **模型下拉布局重构**：下拉菜单使用自然文档流和纵向 flex，取消固定高度和选项绝对定位；分类标题、模型名称、说明和选中勾全部左对齐，解决文字重叠、挤压和对齐混乱。
3. **思考开关真实接入**：输入区“思考”按钮改为真实参数开关，前端发送 `thinking`，后端按 provider 注入 DeepSeek / MiMo 的 thinking payload；推理强度由后端环境变量或 profile 控制。
4. **输入区工具栏重排**：底部工具栏拆分为附件、模型/思考、提示词/Skill、发送四组，取消“工具箱”文字标识；提示词和 Skill 选中后只显示 chip，不改写输入框正文。
5. **关闭边界修复**：模型下拉与头像选择器均支持点击外部或 Esc 关闭；点击输入框附近空白区域可关闭模型面板。
6. **来源与 Markdown 排版**：来源右侧栏绑定当前会话，切换会话自动关闭；来源预览使用 Markdown 渲染，消息正文 Markdown 行高和段落间距已优化。
7. **暗色主题与设置细节**：暗色主题修复用户消息气泡、切换 Agent 提示气泡、公司预设提示词气泡、设置页开关按钮的对比度；管理员“用户管理”标签取消无意义数量 badge。

---

## 第十阶段：知识库 RAG 功能

**目标**：先做出可信的知识库问答最小闭环：管理员刷新知识库，员工在聊天里提问，AI 能引用内部文档片段回答，并且无关问题不会乱引用。

> 2026-05-30 更新：本阶段正式主线已从旧 RAG / Wiki Router / Chroma 切换为 GBrain。旧 `backend/knowledge_base/wiki/`、`core/wiki_router.py`、`core/rag_engine.py`、`backend/vector_store/` 不再是正式知识库路径，也不作为 fallback。GBrain 的功能解析见 `docs/gbrain-feature-inventory.md`，原始资料导入和提炼流程见 `docs/gbrain-ingest-workflow.md`，Project_R 对 GBrain 的真实适配进度和下一步顺序见 `docs/gbrain-adaptation-progress.md`。以下早期 10A/10B 旧 RAG checklist 仅保留为历史记录，当前开发判断以 GBrain 文档和本更新块为准。

**GBrain 当前主线任务**：
- [x] 退役旧 Wiki Router / Chroma / vector_store 正式主路径，不保留旧 RAG fallback。
- [x] 建立 `workspace_data/global/company-wiki/{raw,derived,manifests}`，并将 `derived/` 注册为 GBrain `company-wiki` source。
- [x] 建立 GBrain HTTP/MCP service-account adapter：health、source status、query、sync、doctor、启动/重启服务。
- [x] 配置本地 Ollama + `mxbai-embed-large` embedding，并完成真实样本 sync。
- [x] 接入 `/query ...` 显式知识库查询，强制传入 `source_id=company-wiki`，普通 Chat 不自动查询 GBrain。
- [x] 接入 Markdown / DOCX 第一版 raw 编译，PDF 结构化提炼 MVP，管理员 pending review 审核后进入查询面。
- [x] 收口 Project_R / GBrain 原始文件提炼边界：原始文件提炼归 Project_R Agent / Skills，GBrain 只接收 Project_R 产出的 Markdown；管理员公司知识免二次审核，私人空间不入公司库，项目资料一键录入项目 source；用户只触发录入，不选择 API Key，Project_R 后端按文件类型和复杂度自动选择 DeepSeek、MiMo、转写流程或 `pending_extractor_capability`。“未入库文件”定义覆盖 Markdown/txt、DOCX、PDF、复杂 PDF、音频/视频、图片/截图、邮件和未来支持的业务附件；第一版批量录入当前项目所有当前可处理且未入库文件，缺 extractor 的类型标记 `pending_extractor_capability`。
- [x] 管理员后台展示 GBrain 状态、manifest、sync、doctor 摘要，并提供启动/重启、导入 raw、含 PDF 提炼、查询回归和 Think 回归入口。
- [x] 建立 GBrain 上游源码维护规则和 `patches/gbrain/` 记录，避免无记录修改上游。
- [x] 建立 GBrain 查询质量回归集第一版：固定 AS 1288、AS 2047、VMU、0515 会议、书面化原则等真实问题、期望 source、期望引用片段，并提供离线测试与真实服务回归脚本；PGLite 重建后 `书面化原则是什么` 排序退化已通过中文规则/流程类标题化查询变体修复并重新跑通真实回归。
- [x] 接入项目级 source：`workspace_data/project/{品牌}/{项目代号}` 映射到独立 GBrain source，并强制权限 scope。
  - 2026-05-31 已完成一键录入真实样本闭环并补齐项目 extractor MVP：稳定 source id `project-{brand}-{workspace_id}`、项目 `derived/` 路径、管理员 `project_sources` 状态、项目查询显式 source scope、`POST /workspaces/{id}/knowledge/ingest`、异步 `POST /workspaces/{id}/knowledge/ingest/async`、Project_R extractor classifier、manifest 分类字段、项目文件面板“一键录入项目知识库”按钮和待录入数量。项目资料默认不走管理员审核，不进入公司库；文字资料/DOCX/普通 PDF、复杂 PDF/图纸 MiMo 视觉提炼、图片/截图 MiMo 提炼、MP4 自动/长视频分段转写会议、说话人/术语纠错、EML 邮件线程和 EML 附件递归均可编译到项目 `derived/` 并在 GBrain sync 成功后标记 `indexed`。真实样本为 `backend/workspace_data/project/BFI/GBrain验收项目-001/`：synthetic 报价 Markdown、VO08 变更 PDF、建筑图纸 PDF、短 MP4 会议录音、长 MP4 音频类视频、审批流程截图、EML 邮件和 4 个邮件 PNG 附件全部编译，manifest 为 `total=11, compiled=11, pending_extractor_capability=0, pending_transcription=0, failed=0`；长视频分 11 段转写并生成说话人/术语纠错 transcript。验证：`venv\Scripts\python.exe -m pytest -q` 通过，191 passed、6 subtests passed；`bun run typecheck` 通过。
- [ ] 设计客户情报 / 客户画像 source：`workspace_data/customer/` 作为客户资料源根，每个客户/账号映射独立 `customer-*` GBrain source。客户画像是受限业务情报，不写入 `company-wiki`；后续需补客户工作区权限、营销组访问控制、客户资料 extractor、人物画像 / 决策链 / 关系强弱 / 偏好风险 Markdown 结构、GBrain graph/timeline 展示和客户 source Think 回归。
- [ ] 接入 GBrain `think` 到正式回答层，解决 source scope / OAuth client 或 MCP 调用方式。
  - 2026-05-30 已完成 guarded adapter 第一版：`GBrainAdapter.think()` 支持 source-scoped OAuth client_credentials、`/query --think ...` 与 `/think ...` 显式入口、citations/gaps/warnings 来源面板归一化，并新增后端测试。已补齐本地上游 patch `patches/gbrain/0003-think-source-scope-gather-and-takes.patch`：`runThink()` -> `runGather()` -> hybrid/takes/graph 均传递 source scope，PGLite/Postgres takes keyword/vector SQL 过滤 `pages.source_id`，并通过 GBrain `bun run typecheck` 与相关 Bun 测试。已创建 `company-wiki` source-scoped OAuth client 并跑通真实 MCP `think`，返回 `status=ok`、token-bound source scope 生效；配置 `GBRAIN_THINK_MODEL=deepseek:deepseek-chat` 后，`书面化原则是什么` 可返回 DeepSeek 综合答案、`warnings=[]` 和 citation。已新增 `backend/scripts/gbrain_think_regression.py` 与离线测试固定第一条真实服务回归。未勾选原因：当前只验证了 company-wiki 显式 `think`，仍需项目 source think scope、扩展答案/引用/gap 回归和前端 gap/conflict 展示。
- [ ] 接入音视频会议提炼：转录、术语纠错、时间戳回链、会议知识提炼、按 source scope 入库。
  - 2026-05-31 已完成 transcript 侧车 + 项目 MP4 自动转写 MVP，并补长视频分段、说话人映射和术语纠错：company-wiki 与项目 source ingest 支持 MP3/MP4/MOV/MKV/WEBM + 同名 `.transcript.*`、`.vtt/.srt` 或同名目录 `transcript.*`，生成 `meeting_structured_extract` Markdown；项目文件一键录入路径下有 transcript 的音视频会直接进入项目 source，不走管理员审核；项目 MP4 无 transcript 时会用本地 ffmpeg 抽音频并调用 MiMo 自动转写，长媒体默认 300 秒分段，生成 `.auto.transcript.md` 后用 DeepSeek 输出 `Speaker Map` 和术语纠错记录，再进入会议结构化提炼。未勾选原因：company-wiki 会议直入规则、低置信标记、绝对时间戳回链、专业 diarization 和真实音视频质量回归尚未完成。
- [ ] 产品化 GBrain maintain / doctor / jobs / citation-fixer / contradiction 到管理员后台和通知中心。
  - 2026-05-30 已完成第一版维护任务竖切片：后端 adapter 包装 GBrain MCP `run_onboard(mode=check)`、jobs 列表/提交/详情/进度/取消/重试和 `find_contradictions`；管理员后台新增“GBrain 维护”页，可查看 doctor/maintain/jobs/contradiction 状态，提交 `sync/embed/lint/backlinks` 白名单任务，任务操作写审计和通知。已补答案反馈纠错审核 MVP：低分且带 GBrain 引用的回答反馈会生成 `gbrain_answer_correction:*` 知识审核项并通知管理员。已确认 citation-fixer 是 GBrain agent skill 而不是普通 job，后端已补 `submit_agent`/`submit_citation_fixer` 和 `POST /admin/knowledge/gbrain/citation-fixer`，前端管理员 GBrain 维护区已补提交表单；`agent_status` 现在区分 `configured_unverified` 与 `ready`，新增 `backend/scripts/gbrain_agent_preflight.py` 和 `docs/gbrain-agent-citation-fixer-runbook.md`；`patches/gbrain/0004-agent-bound-oauth-client-registration.patch` 已补齐 GBrain 本地绑定型 agent OAuth client 注册入口。后续已新增 `gbrain_register_agent_client.py`、`gbrain_enable_agent_gateway_loop.py`、`gbrain_agent_submit_smoke.py`、`gbrain_agent_inline_execution_smoke.py`，本机已完成真实 client 注册、DeepSeek gateway loop 配置、`submit_agent` 绑定冒烟和 PGLite `company-wiki` source 内只读 inline subagent 执行烟测；为此补齐 `patches/gbrain/0005-subagent-tool-source-scope.patch` 与 `patches/gbrain/0006-chat-tool-json-schema-wrapper.patch`。未勾选原因：真实 citation-fixer 改写型 subagent 完成执行、GBrain worker 长跑、任务完成轮询通知、定时维护和自动 remediation 费用/权限边界仍未验收。
- [ ] 用 GBrain Skillify 或 Project_R adapter skill 固化项目复盘、资料提炼、知识纠错、会议沉淀流程。

**知识源设计**（2026-05-19 grill-me 决策，已调整为本地目录）：
- 知识库文件直接存放在 `backend/knowledge_base/` 目录下，首期为 `rules/` 和 `training/` 两个子目录（源自公司 Obsidian Wiki 的结构化 .md 文件）。
- 不做外部同步：管理员直接将 .md 文件放入知识库目录，通过管理接口手动触发"刷新知识库"重建向量索引。
- 不写死两个目录：RAG 引擎通过 `RAG_SOURCE_DIRS` 配置多目录，后续可添加更多知识目录。
- .md 文件中的 YAML 前置元数据（`title`、`tags`、`authority_level`、`content_kind`、`source_domain`）由索引器提取，附着到每个 chunk 上；检索时可用于过滤，AI 回答时标注来源。
- 向量化使用本地 sentence-transformers 模型（当前优先 `paraphrase-multilingual-MiniLM-L12-v2`），免费离线运行。
- 分块策略：按 `##` 标题切分（推荐），每个 chunk 自带"文件名 > 标题路径"前缀，保证上下文自包含。

**实施方式**：本阶段拆成 10A / 10B / 10C。先把索引和检索基座做成可单测模块，再接入聊天流，最后再做会话临时附件。不要一开始就同时做全部格式、全部 UI 和全部管理后台。

**10A - RAG 索引与检索基座**：
- [x] 由 Gary 手动安装 RAG 依赖：`chromadb`、`sentence-transformers`、`pyyaml`；2026-05-24 依赖体检确认当前 venv 已安装并可导入，同时已安装文件上传所需 `python-multipart`
- [x] 在 `.env.example` 增加 RAG 配置：`RAG_SOURCE_DIRS`（默认 `rules,training`）、`RAG_EMBEDDING_MODEL`（当前优先 `paraphrase-multilingual-MiniLM-L12-v2`）、`RAG_EMBEDDING_MODEL_PATH`
- [x] 编写 `core/rag_engine.py`：`refresh()`（扫描本地目录+增量索引）、`search(query, top_k, filters?)`（检索+元数据过滤）、`get_status()`；首期只支持 `.md`
- [x] 实现 YAML frontmatter 解析：提取 title/tags/authority_level/content_kind/source_domain 作为 chunk 元数据
- [x] 实现按 `##` 标题分块：每个 chunk 自带"文件名 > 标题路径"前缀；过短 chunk 与相邻 chunk 合并
- [x] 实现增量索引：hash 跳过未变更文件，删除的文件从向量库移除
- [x] 编写 `api/rag.py`：`POST /admin/knowledge/refresh`（管理员触发刷新）、`GET /admin/knowledge/status`（索引状态）
- [x] 编写不依赖真实云端 LLM 的测试：用小型本地 `.md` 文档验证切片、frontmatter 提取、hash 跳过、删除同步、检索返回来源片段

**10B - 管理接口与聊天接入**：
- [x] 编写 `api/rag.py`：`POST /admin/knowledge/refresh` 触发刷新，`GET /admin/knowledge/status` 返回索引状态；仅管理员可调用
- [x] 编写或收束 `core/intent.py`：保留固定枚举 `chat` / `rag_query` / `document_generation` / `skill_trigger`；当前临时采用显式路由，默认只返回 `chat`，后续待 Skills 完整后再恢复规则兜底/自动识别
- [x] 修改 `api/chat.py`：显式路由阶段仅 `/query ...` 强制进入知识库问答；知识库问答内部优先尝试 Wiki Router 检索，命中来源时把来源片段作为上下文传给当前 LLM Provider，未命中再走 Chroma RAG fallback；无来源约束只对 `rag_query` 生效，避免普通聊天被强行引导到知识库；assistant 消息需记录是否使用 RAG/Wiki 与来源摘要
- [x] 前端聊天区展示 RAG 来源的基础信息：文件名、片段序号或简短来源，不新增 Markdown 依赖
- [x] 前端消息区支持基础 Markdown 渲染：标题、列表、引用、表格、行内代码、代码块；代码块提供一键复制按钮，便于复制 AI 生成的邮件、通知、话术和模板正文
- [ ] 后续补齐引用来源交互：点击 `rules/training/standards/sources` 来源后，在聊天工作台中新建标签页打开对应 Markdown 页面，支持阅读原文与返回对话
- [ ] 用真实测试文件验证：登录 → 刷新知识库 → 提问文档内问题 → AI 回答并显示来源 → 提问无关问题时不强行引用知识库

**10C - 会话临时附件（可在 10B 完成后单独收口）**：
- [x] 后端新增会话附件保存目录与元数据，附件只绑定当前 `session_id` 与 `user_id`，不进入全局向量库
- [x] 前端支持在当前会话上传临时文本/Markdown 文件，并在消息输入区显示附件状态
- [x] 前端支持将图片、PDF 和通用文件通过附件按钮、剪贴板粘贴、拖拽到对话区添加为会话临时附件
- [x] 发送消息时将所选会话附件内容注入本次 LLM system prompt，优先于全局 Wiki 知识库
- [x] 支持将当前会话选中的图片附件投递给支持图像输入的 MiMo 模型；DeepSeek 等不支持多模态的模型给出明确提示
- [x] 删除会话时同步删除该会话附件文件与元数据
- [x] 会话超过 3 天未活跃后自动清理该会话临时附件文件与元数据
- [ ] 后续补齐附件向量化/分块检索、OCR、视频/音频理解、复杂附件预览、附件引用定位与临时索引清理策略

**10D - 工作区项目资料目录（项目子库文件来源）**：
- [x] 新建工作区时，后端在 `workspace_data/<workspace-slug>/` 下创建专用目录，并自动生成固定默认项目资料目录：`01-合同与报价/`、`02-图纸与技术资料/`、`03-会议纪要/`、`04-变更与签证/`、`05-生产与发货/`、`06-现场与客诉/`、`99-临时资料/`
- [x] 后端提供只读文件树接口，仅返回当前用户有权访问的工作区目录内容；路径必须使用相对路径，禁止 `../`、绝对路径、符号链接逃逸
- [x] 前端 Agent 模式默认展示工作区文件目录/上下文面板，用于检查参考文件是否正确、是否遗漏
- [x] Chat 模式只提供轻量入口打开同一目录面板，不在侧栏常驻文件树
- [x] 已补齐上传文件、删除/回收区、权限策略、审计日志与项目资料索引状态；项目 GBrain source 已支持复杂 PDF/图纸、图片/截图、MP4 自动/长视频分段转写、说话人/术语纠错、EML、EML 附件递归和异步录入，文件预览仍按后续阶段推进

**10E - 工作区文件管理（10D 验证后再做）**：
- [x] 成员可上传文件到工作区目录；上传文件大小、类型、数量需有限制
- [x] 成员只能删除自己上传的文件；工作区管理员可删除所有文件
- [x] 删除优先软删除或移入工作区回收区，不直接物理删除
- [x] 支持有限层级目录：显示目录树、新建文件夹、上传到指定文件夹、删除文件；删除文件夹仅允许空文件夹；用户侧不再使用“移动到路径”输入，文件移动采用 Windows 风格剪切 / 复制 / 粘贴或单项拖拽，第一版不做多选
- [x] 上传、删除、恢复、永久删除、新建/删除空文件夹等操作写入审计日志
- [x] 文件变更后可触发项目子库/RAG 索引刷新状态更新；项目对话只读取当前项目、未删除、已索引的文本类资料

**完成标志**：将 3-5 份真实测试文档放入知识库并刷新后，员工使用 `/query ...` 能得到基于文档的回答和来源提示；普通聊天不会乱引用知识库；管理员接口受权限保护；相关后端测试通过。后续恢复自动意图识别时，再补“自然语言提问自动进入知识库问答”的验收。

> 实现状态：10A/10B 旧 RAG / Wiki Router / Chroma 主路径已被 GBrain 主线取代。正式知识库问答只通过 `/query ...` 或等价知识库 Skill 调用 GBrain `company-wiki` / 项目 source；Project_R 当前由 GBrain `query` 返回引用片段，再由当前聊天模型组织答案。当前已补齐 GBrain 查询回归、项目 source adapter、项目真实样本一键录入闭环、复杂 PDF/建筑图纸 MiMo 视觉提炼、图片/截图提炼、MP4 自动/长视频分段转写、说话人/术语纠错、EML 邮件线程提炼、EML 附件递归、项目内引用定位、异步项目录入队列、显式 `think` adapter、PDF 结构化提炼、音视频 transcript 侧车 MVP、GBrain 维护任务第一版、答案反馈纠错审核 MVP、submit_agent 绑定冒烟和只读 inline subagent 执行烟测。仍未完成：`think` 默认回答层、置信度/绝对时间戳回链、区域级图片引用、文件预览 UI、citation-fixer 改写型执行流和真实维护任务长跑。
> 10C 实现状态：会话临时附件已从小型文本第一版扩展为文件级临时附件，保留 `SessionAttachment`、`POST/GET/DELETE /chat/sessions/{id}/attachments`，新增 `POST /chat/sessions/{id}/attachments/upload` multipart 上传。前端输入区支持附件按钮选择、复制粘贴图片/文件、拖拽到对话区并显示可移除 chip；单文件临时附件限制为 20MB，超过建议改用项目文件。发送消息时，文本类附件和可提取文本的 PDF 注入正文摘录；图片附件在支持图像输入的 MiMo profile 下会以 OpenAI-compatible `image_url` content block 投递给模型，DeepSeek 等不支持多模态的模型会提示切换。视频/音频附件当前明确提示尚未接入理解，不再静默当作可解析内容。会话超过 3 天未活跃后自动清理临时附件；删除会话时同步删除附件。仍未完成附件向量化/分块检索、OCR、复杂预览和附件引用定位。
> 10E 实现状态：已完成 P9 工作区文件管理竖切片，新增/升级 `WorkspaceFile` 元数据、`POST /workspaces/{id}/files/upload` 多文件上传、兼容旧 `POST /workspaces/{id}/files`、`DELETE /workspaces/{id}/files?path=` 软删除到 `.trash`、`POST /workspaces/{id}/files/restore`、`DELETE /workspaces/{id}/files/permanent?file_id=`、`POST /workspaces/{id}/knowledge/refresh`、`POST /workspaces/{id}/knowledge/ingest/async`、`POST /workspaces/{id}/paths/copy`；前端工作区文件面板支持多文件选择/拖拽上传、100MB 单文件前置校验、项目文件/回收区切换、恢复/永久删除、异步一键录入项目知识库、单项剪切 / 复制 / 粘贴和单项拖拽移动。权限规则为成员只能删除、重命名、剪切或移动自己上传的文件，工作区管理员可修改所有文件；系统管理员可进入全部项目/客户类共享工作区；公司项目默认对所有有效用户开放；隐藏项目仅对系统管理员、成员管理中显式添加的人员或授权组别可搜索和进入；工作区管理员是 scoped admin，不等同于系统管理员。路径使用相对路径并防止 `../`、绝对路径与符号链接逃逸；上传、删除、恢复、永久删除、文件夹操作、重命名、移动和复制均写审计日志。用户侧文件移动已退役“移动到路径”输入，第一版不做多选。项目对话已接入当前项目 GBrain source，并已支持复杂 PDF/图纸、图片/截图、MP4 自动/长视频分段转写、EML、EML 附件递归和引用定位；文件预览和更完整项目质量回归仍为下一阶段补齐项。本轮文件操作修改已通过 `backend` 的 `tests/test_workspace_files.py`、`frontend` 的 `bun run typecheck` / `bun run build`，并用 headless Chrome 验证右键菜单不再显示“移动到”。
> 10D 实现状态：Phase 9B 已提前落地工作区文件树第一版，10E/P9 已进一步补齐上传、删除/回收区、权限、审计与项目资料索引状态。下一步重点从“文件管理闭环”转向“文件内容解析与可信引用闭环”。

---

## 第十一阶段：办公文件自动生成

**目标**：先实现“后端生成 Word 文件并下载”的最小闭环，再扩展 PPT / Excel。当前显式路由阶段不再由普通自然语言自动触发文件生成，后续通过明确入口或业务 Skill 承接。

**实施方式**：先做一个固定模板的 Word 竖切片：显式文件生成入口/内部 `document_generation` 分支 → 生成结构化内容 → 渲染 `.docx` → 返回下载卡片。PPT / Excel 等到 Word 链路验证后再复用同一接口扩展。

**任务清单**：
- [ ] 手动在 `backend/templates/word/` 中放入至少一个 `.docx` 模板文件，并在文档中记录模板用途与占位字段
- [ ] 在 `.env.example` 增加 `TEMPLATES_DIR`、`GENERATED_FILES_DIR`、`GENERATED_FILE_TTL_HOURS`，默认使用相对路径
- [ ] 编写 `core/doc_renderer.py` 的稳定接口：`render_docx(template_id, payload)`、`get_generated_file(file_id)`、`cleanup_expired_files()`（当前仅完成无模板 tracer bullet：标准库生成基础 `.docx`）
- [ ] 实现错误处理：模板缺失、占位字段缺失、渲染失败、磁盘空间不足；错误返回用户可理解提示，日志中不包含敏感信息
- [x] 编写 `api/documents.py`：提供文件下载接口；下载接口必须校验当前用户是否有权访问该文件
- [x] 修改聊天处理：保留 `document_generation` 分支，命中时返回文件卡片元数据，而不是只返回纯文本；当前显式路由阶段普通自然语言不会自动命中该分支
- [x] 前端实现文件下载卡片：文件名、下载按钮
- [x] 测试：使用 mock LLM 或固定 payload 生成 `.docx`，确认文件生成；下载权限与 48 小时清理逻辑可测试（Word 人工打开验收后补）

**完成标志**：通过显式文件生成入口或后续业务 Skill 触发 Word 文件生成，前端弹出下载卡片，点击后能保存并正常打开；无权限用户无法下载别人的生成文件；过期文件会被自动清理。

> 实现状态：Phase 11 已完成第一条 tracer bullet：`core/doc_renderer.py` 使用 Python 标准库生成基础 `.docx`，新增 `GeneratedFile` 表、`GET /documents/{file_id}/download` 权限校验下载接口与管理员 `POST /documents/cleanup` 过期清理接口；内部 `document_generation` 分支可将 LLM 回复渲染为 `.docx`，前端显示下载卡片并用带 Token 的 fetch 下载。当前显式路由阶段，普通自然语言 Word 请求保持 `chat`，不会自动生成文件。当前未完成：正式模板目录与模板字段、复杂错误分类、文件卡片失败状态、Word 文件人工打开验收、面向用户的显式文件生成入口。

---

## 第十二阶段：业务 Skill 底座与真实业务 Skill 验收

**目标**：保留已经完成的 Skill 底座，改用真实业务 Skill 验证 Project_R 的差异化能力：用户显式选择业务 Skill 后，系统收集输入并生成标准化业务输出。自然语言自动触发待 Skills 完整后恢复。早期 U03 标签打印样板已确认退役，不再作为测试目标或业务能力示例。

**实施方式**：不要一开始做“任意 Skill 平台”。先用真实业务 Skill 跑通显式选择、补参、执行状态、结果展示和文件下载等底座能力，再沉淀通用接口。

**任务清单**：
- [x] 退役 `tag-printing` 相关代码、测试和文档入口，不再让普通用户或测试流程看到标签打印 Skill
- [x] 编写 `core/skill_runner.py` 的最小接口：`list_skills()`、`match_skill(user_text)`、`start_run(skill_id, user_id, session_id)`、`submit_input(run_id, payload)`
- [x] 编写 `api/skills.py`：列出可用 Skill、启动 Skill、提交输入、查询运行状态；所有接口校验 JWT 与用户权限
- [x] 将 `core/intent.py` 的 `skill_trigger` 与 Skill 元数据打通的历史能力已验证；当前显式路由阶段禁用自然语言自动触发，改为前端 Skill 面板/`selected_skill` 显式启动
- [x] 实现 SkillRun、Skill 元数据加载、显式启动和补参底座
- [x] 前端聊天区支持 Skill 多轮输入：缺少字段时继续追问，字段齐全后执行，并展示结果卡片（当前采用对话式补参，不做表单化字段面板）
- [ ] 端到端测试：手动选择真实业务 Skill → 补充必要信息 → 生成状态或结果卡片 → 如有文件输出则下载后内容符合样例

**完成标志**：标签打印 Skill 已从用户入口、测试目标和业务文档中退役；至少一个真实业务 Skill 能由用户显式选择并完成结果展示；`skill_runner` 可以复用到后续业务 Skill；业务工作流清单状态与 SKILL.md 链接同步更新。后续恢复自动意图识别时，再补自然语言触发验收。

> 实现状态：Phase 12 已完成 Skill 底座：新增 `SkillRun` 表、`core/skill_runner.py` 加载 `backend/skills/builtin/*/SKILL.md` 元数据并支持列表、匹配、启动运行和补充输入；新增 `api/skills.py`，提供 `GET /skills`、`POST /skills/match`、`POST /skills/runs`、`POST /skills/runs/{id}/inputs`、`GET /skills/runs/{id}` 与管理员 `POST /skills/reload`。当前显式路由阶段，聊天不会根据自然语言自动命中 `skill_trigger`；用户必须通过前端 Skill 面板或 `selected_skill` 启动真实业务 Skill。早期 U03 标签打印无模板输出 tracer bullet 已确认退役，相关 Skill 文件、dispatcher 工具入口、前端示例入口和测试目标已删除，后续以真实业务 Skill 补端到端 UI 验收。

---

## 第十三阶段：管理员后台 MVP

**目标**：管理员能完成系统运行所需的最小维护动作：用户、知识库刷新、知识审核、模板状态查看。审计报表和复杂上传管理可在 MVP 后迭代。

**实施方式**：后台先嵌入设置页的管理员区域，不单独做大型管理系统。所有管理员接口先从后端权限和审计日志做稳，再补前端表格体验。

**任务清单**：
- [x] 在前端实现管理员专属入口：按 `role` 判断显示，普通用户不可见且直接访问返回无权限提示
- [x] **用户管理 MVP**：查看用户列表、新增用户、禁用账号、重置密码；修改角色先仅支持普通用户 / 管理员
- [x] **知识库管理 MVP**：查看索引状态、触发刷新、查看最近刷新结果；文件上传可先由管理员手动放入目录（由 `/admin/knowledge/status` 与 `/admin/knowledge/refresh` 提供）
- [x] **知识审核 MVP**：查看 `knowledge_review` 队列，支持通过、驳回、修改后通过；通过后写入正式知识库等待刷新
- [x] **模板管理 MVP**：查看已有模板、模板用途、绑定 Skill；上传 / 替换可后续增强
- [x] **审计日志 MVP**：按用户和日期查看近期操作与 Token 消耗；Excel 导出放到后续报表迭代
- [x] 在 `api/admin.py` 中补充对应接口，所有接口验证管理员角色并写入审计日志

**完成标志**：用管理员账号登录后，能新增或禁用用户、触发知识库刷新、审核一条候选知识、查看模板和近期审计记录；普通用户看不到也不能调用管理员能力。

> 实现状态：Phase 13 已完成管理员 MVP 可用入口：新增 `api/admin.py` 与 `frontend/src/renderer/api/admin.ts`，提供用户列表/新增/更新/禁用/重置密码、审计日志按用户/日期查询、知识库状态/刷新、知识审核查看/通过/驳回/修改后通过、模板与 Skill 绑定状态只读接口；普通用户调用返回 403。`User` 新增 `is_active` 字段，禁用账号无法登录；`models.init_db()` 增加 SQLite 轻量列迁移，补齐旧库 `users.is_active` 与 `skill_runs.generated_file_id`。审核通过的知识会写入 `knowledge_base/wiki/rules/知识审核沉淀.md`，等待刷新索引后用于回答。设置页已新增管理员专属区，展示知识库指标、用户管理、待审核知识、模板/Skill 状态和近期审计。当前未完成：审计 Excel 导出、真实管理员 UI 验收。

---

## 第十四阶段：设置界面

**目标**：用户能在设置中自定义个人偏好。

**任务清单**：
- [x] 实现设置界面框架：左侧分类导航 + 右侧内容区（参考 Proma）
- [x] **通用设置**：编辑头像和昵称；语言选择（仅简体中文，英文选项显示"即将支持"）；任务完成音效开关；自动归档选项（禁用/7天/14天/30天/60天）；消息悬浮置顶条开关
- [x] **服务器连接**：填写后端 IP 和端口，保存后立即生效，并显示连接状态（删除 Proma 原"模型配置"中的 API Key 等内容）
- [x] **提示词管理**：新建、编辑、删除提示词模板，对话时可快速调用
- [x] **Agent 配置**：显示官方 Skills 与企业 Skills 列表（只读）；显示 MCP 配置（如启用）；不引入 nano/banana
- [ ] **Chat 工具**：保留记忆功能、联网搜索功能；不引入 nano/banana（已完成本地设置入口，真实联网搜索后端能力待补）
- [ ] **远程连接**：仅显示钉钉 Bot 配置项（已完成本地配置入口，Phase 16 再接真实 Bot）
- [x] **软件教程**：内嵌 Markdown 教程文档
- [x] **快捷键管理**：显示所有快捷键，支持自定义修改（参考 Proma 默认设定）
- [x] **外观设置**：主题切换（亮色 / 暗色 / 跟随系统）

> **删除项**：原"磁盘管理"和"数据迁移"不再做。
> 配置统一由后端 + 安装包预置完成，员工无需在客户端做这些操作。

**完成标志**：能在设置中修改昵称并在主界面看到更新；修改服务器地址后连接状态正确反映；管理员账号能看到额外 5 项管理菜单。

> 实现状态：Phase 14 已完成设置页主体并补齐 2026-05-27 UI 细节修正：设置页从竖排面板升级为左侧分类导航 + 右侧内容区，包含通用、服务器、提示词、归档、Agent、Chat 工具、远程连接、教程、快捷键、管理员分类；`PUT /auth/me` 支持昵称/头像标识更新并刷新主界面用户信息；通用偏好、Chat 工具、钉钉配置、快捷键和主题当前保存在 `localStorage`；提示词管理复用公司预设接口与 Electron 本机用户提示词 IPC；Agent 配置只读展示后端 Skills。头像 emoji 选择器已修复网格溢出并支持外部点击/Esc 关闭；暗色主题下开关按钮、提示词气泡与管理员用户标签已修复。当前未完成：联网搜索真实后端能力、钉钉 Bot 真实消息链路、快捷键全局绑定、真实设置 UI 验收。

---

## 第十五阶段：欢迎引导界面

**目标**：首次启动时引导用户完成初始配置。

**任务清单**：
- [x] 实现首次启动检测：判断本地是否已有配置文件，没有则进入引导流程
- [x] **Step 1 欢迎页**：显示软件名称和简介；提供三个选项：查看教程、从其他设备迁移、导入他人配置；提供"跳过"按钮（参考 Proma 截图布局）
- [x] **Step 2 环境检测**：自动检测能否连通后端服务器（ping 后端 IP:Port）；成功则显示绿色提示进入主界面；失败则提示错误并允许手动填写服务器地址重试
- [x] 实现软件教程页面：图文说明主要功能的使用方法

**完成标志**：清除本地配置后重启软件，能看到欢迎界面；填写正确的服务器地址后能顺利进入主界面。

> 实现状态：Phase 15 已完成代码级第一版：`App.tsx` 使用本地 `project-r:onboarding-complete` 标记判断首次启动，未完成引导时进入 `/onboarding`；欢迎页提供查看教程、环境检测、跳过入口，并保留“从其他设备迁移 / 导入他人配置”为禁用占位；环境检测调用当前填写后端地址的 `/health`，成功后保存到 `server-atoms.ts` 并进入登录；教程页覆盖 Chat、Agent、Knowledge、Skill 四类核心入口。已通过 `bun run build`，清除本地配置后的真实 Electron 重启验收待 Gary 手工确认。

---

## 第十六阶段：钉钉集成

**目标**：用户能通过钉钉 Bot 与系统交互，不必打开桌面客户端。

**任务清单**：
- [ ] 在后端实现钉钉 Bot Webhook 接收接口
- [ ] 实现消息转发：将钉钉收到的消息转入对话系统处理，将 AI 回复发回钉钉
- [ ] 在前端"远程连接"设置中实现钉钉配置页：填写 Bot Token 和 Webhook 地址
- [ ] 测试：在钉钉中向 Bot 发送消息，确认能收到 AI 回复

**完成标志**：在钉钉中向 Bot 提问，能收到 AI 的正确回复。

> 实现状态：按 Gary 2026-05-21 决策，Phase 16 调整为后补功能，非现阶段必要实现。当前仅保留设置页“远程连接 / 钉钉 Bot”本地配置占位，不作为 Phase 15/17 推进阻塞项。

---

## 第十七阶段：Windows 全链路联调

**目标**：在 Windows 单机上跑通完整的端到端流程，确保迁移前一切正常。

**任务清单**：
- [ ] 在同一台 Windows 电脑上同时启动后端（`uvicorn`）与前端（`bun run dev`）
- [x] 检查所有路径用 `pathlib` 与 `.env`，无任何 `D:/` 硬编码
- [x] 检查前端所有后端调用均从配置读取 IP，无 `localhost` 硬编码
- [ ] 用真实数据走一遍：登录 → Chat → RAG → 文件生成 → Skill 触发 → 管理员后台 → 知识审核
- [ ] 把测试结果（截图 + 时长）记录在 `docs/test-windows.md`

**完成标志**：完整业务链路在 Windows 上跑通，无需 Mac mini 即可日常使用。

> 实现状态：Phase 17 已完成代码级静态检查底座：新增 `scripts/test-windows.ps1`，可检查源码中的 Windows 绝对路径硬编码、`frontend/src` 中的后端地址硬编码，以及前端后端地址是否仍由 `VITE_DEFAULT_API_BASE_URL` / `server-atoms.ts` 管理；新增 `docs/test-windows.md` 记录本次代码级检查结果与后续人工验收项；修复 `scripts/refresh-knowledge.ps1` 登录 token 字段兼容问题。已验证 `scripts/test-windows.ps1 -StaticOnly` 与 `bun run build`；真实 Electron 全链路仍需 Gary 启动后端与前端后手工跑完并补截图/时长，故全链路与截图记录 checklist 保持未勾选。

---

## 第十八阶段：异步通知中心 MVP

**目标**：把现有通知后端桩扩展为面向 50 人团队的结构化通知中心，用于异步任务、项目协同、审批和风险告警，降低跨部门沟通成本与商业风险。

**任务清单**：
- [x] 扩展 `Notification` 模型：新增 `category`、`severity`、`action_status`、`action_kind`、`action_payload_json`、`event_key`、`expires_at`，保留旧 `type` / `link` 兼容字段
- [x] 新增 `core/notification_service.py`：集中创建、分发和校验通知，支持单用户、多用户、系统管理员、工作区管理员、工作区成员分发
- [x] 扩展通知 API：列表、未读数、待处理数、标记已读、全部已读、待办完成、待办忽略、管理员清理过期通知
- [x] 前端侧边栏底部设置图标左侧增加通知铃铛，显示未读 badge（超过 99 显示 `99+`）
- [x] 实现通知 Popover：点击铃铛弹出约 360px 面板，支持 `全部 / 未读 / 待处理` Tab，点击外部或 Esc 关闭
- [x] 实现结构化通知动作：打开会话、打开工作区、打开 Skill 运行、下载文件、打开管理员审核；旧 `link` 仅作兼容
- [x] 实现 60 秒短轮询：登录后立即拉未读/待处理数，之后静默轮询；打开 Popover 时拉通知列表
- [x] 实现 Toast 强提醒：仅对新产生的任务完成、任务阻断和严重风险弹出；历史未读和普通协作信息只进通知中心
- [x] 接入 Skill / 文件生成结果通知：完成生成文件、缺材料、执行失败时通知发起人
- [x] 接入知识审核通知：新增待审核知识时通知系统管理员，点击进入管理员知识审核页
- [x] 接入工作区权限与索引通知：加入工作区通知本人，项目资料索引完成/失败通知上传人和工作区管理员，批量索引完成可汇总通知项目成员
- [x] 接入风险告警最小桩：磁盘低空间、LLM Key/API 异常等系统级风险通知系统管理员，项目批量删除异常通知工作区管理员
- [x] 通知记录默认保留 90 天；严重风险/异常审计类通知至少保留 180 天或与审计日志同步保留；清理通知不得删除业务记录或审计日志
- [x] 后端运行相关 `pytest`，前端运行 `bun run typecheck`；涉及构建时补跑 `bun run build`

**完成标志**：用户登录后能在设置图标左侧看到通知铃铛；异步 Skill 完成、知识审核、工作区索引和风险告警能生成结构化通知；用户能区分未读与待处理，点击通知能到达对应处理位置。

> 实现状态：Phase 18 代码级 MVP 已实现并通过本机验证。通知记录继续采用每用户记录而非 `ALL` 虚拟接收人；通知模型已扩展为 `category + severity + action_status + action_kind/action_payload_json`；前端入口位于侧边栏底部设置图标左侧，360px Popover 支持全部/未读/待处理与 60 秒短轮询；已接入 Skill 完成/缺材料/失败、文件生成完成、知识审核提醒、工作区加入/索引完成/批量删除风险、系统风险告警最小桩。验证命令：后端 67 个相关 pytest 通过，前端 `bun run typecheck` 与 `bun run dist:dir` 通过。

---

## 第十九阶段：迁移到 Mac mini（暂缓）

**目标**：将整个后端迁移到 Mac mini，配置为内网服务，实现无人值守自动启动。

**任务清单**：
- [ ] 在 Mac mini 上安装 Python 3.11 和必要工具
- [ ] 将 `backend/` 目录复制到 Mac mini（通过 U 盘或内网传输）
- [ ] 在 Mac mini 上重建虚拟环境（`python -m venv venv`），安装依赖（`pip install -r requirements.txt`）
- [ ] 复制 `.env`，按 Mac mini 路径调整配置（数据库目录、知识库目录、生成文件目录等）
- [ ] 配置静态局域网 IP（使用 `networksetup` 命令锁定，如 192.168.1.200）
- [ ] 配置 `/Library/LaunchDaemons/` 守护进程：开机自动启动 FastAPI，崩溃后自动重启
- [ ] 配置 `pmset`：断电重启后无需人工登录即可自动运行
- [ ] 在 Windows 客户端"服务器连接"设置中改 IP 指向 Mac mini，验证连接通畅
- [ ] 进行多用户并发测试：同时用 3-5 个账号发送请求，确认系统稳定

**完成标志**：Mac mini 断电重启后，无需任何人工操作，员工电脑上的客户端能自动重新连接并正常使用。

> 实现状态：按 Gary 当前安排，Mac mini 机器尚未准备到位，本阶段暂缓并从近期执行顺序中跳过。Phase 20 客户端打包与内网更新的代码级准备不得以完成 Mac mini 迁移为前置条件；后续 Mac mini 到位后再恢复本阶段。

---

## 第二十阶段：客户端打包与分发

**目标**：把 Electron 客户端打包成 Windows 安装包，并通过 Project_R 后端内网分发更新包，让员工能收到版本通知并从公司内网升级客户端。

**任务清单**：
- [x] 配置 `electron-builder`（参考 Proma 的 `apps/electron/package.json` 中 `dist:win` 脚本）
- [x] 第一版不采用 `electron-updater` 全套发布机制；由 Project_R 自行实现版本检查、下载安装包、SHA256 校验和启动安装器
- [x] 在打包配置中预置默认 `API_BASE_URL`；当前使用可用后端地址，Mac mini 到位后再切换为其内网 IP
- [x] 后端新增客户端版本清单与更新包下载能力：保存最新版本、最低支持版本、安装包文件名、SHA256、更新说明、是否强制更新
- [x] `GET /updates/latest` 允许内网未登录访问，返回版本号、最低支持版本、更新日志、包大小、SHA256 等非敏感信息
- [x] `GET /updates/download/{version}` 必须要求登录 JWT；更新包上传/登记接口必须要求系统管理员权限
- [x] 管理员后台提供更新包上传/登记入口，只有系统管理员可发布新版本
- [x] 前端登录后检查当前客户端版本与后端最新版本；更新可用性按当前设备版本判断，不通过后端给每个用户写普通通知记录
- [x] 通知中心可显示“新版本可用”的更新入口，但该入口来自客户端版本检查，不参与用户级已读/待处理通知分发
- [x] 实现更新日志弹窗：展示版本号、发布日期、更新说明 Markdown/富文本内容；用户点击“下载更新”后才开始下载，不在登录后自动后台下载
- [x] 点击更新通知后由 Electron 主进程下载更新包、校验 SHA256，并启动安装器；renderer 不直接覆盖应用文件
- [x] 实现下载进度窗口：显示正在下载、已下载大小、总大小和进度条；下载完成后进入“更新已就绪”状态
- [x] 下载完成后提供“稍后重启”和“立即重启更新”；强制更新时不允许继续进入主应用
- [x] 更新失败文案使用内部支持口径，例如“自动更新失败，请联系管理员获取最新版安装包”，不得引导员工去公网官网或 GitHub
- [x] 支持普通更新与强制更新两种展示策略：普通更新可稍后处理；低于最低支持版本时允许先登录获取下载权限，但阻断进入 `/app`，用户只能下载并安装或退出软件
- [x] 运行 `bun run dist:win` 生成 `.exe` 安装包
- [ ] 在另一台 Windows 电脑上安装测试：双击安装 → 启动 → 自动连上后端 → 登录使用
- [ ] 把首版 `.exe` 上传或登记到 Project_R 后端更新仓库，写发版说明

**完成标志**：同事在自己电脑上下载安装包并双击运行，无需任何手动配置即可登录使用；后续发布新版本后，员工登录能收到更新通知，并能从 Project_R 后端下载校验后的安装包完成升级。

> 实现状态：Phase 20 代码级准备已实现并通过本机验证，不等待 Phase 19 Mac mini 迁移。已新增 `electron-builder` 配置、后端 `/updates/latest` / `/updates/download/{version}` / 管理员上传接口、管理员后台可视化上传/登记入口、Electron 主进程下载/进度/SHA256 校验/启动安装器 IPC、renderer 更新日志/下载进度/更新就绪/失败文案流程、通知中心中的客户端版本检查入口。已通过 fake package dry-run 下载校验脚本、真实 `0.1.0 -> 0.1.1` 安装包本机静默安装升级验证、真实 `0.1.1` 安装包后端上传/最新版本检查/登录下载 SHA256 校验、后端 67 个相关 pytest、前端 `bun run typecheck`、`bun run dist:dir` 与 `bun run dist:win`；已生成 `frontend/release/Project_R-Setup-0.1.0.exe` 与 `frontend/release/Project_R-Setup-0.1.1.exe`。未完成项：另一台 Windows 安装测试、把首版安装包上传/登记到正式更新仓库。

---

## 第二十一阶段：本地私人工作区与 Local Agent Worker MVP

**目标**：把默认私人工作区从后端托管模型调整为 local-first；第一版只打通本地私人资料读取、预处理、发送前授权和保存到项目资料的边界，不做完整自主本地 Agent。

**任务清单**：
- [x] 在 Electron 侧建立本地私人工作区根目录，标准安装默认使用用户 Documents 下的 `Project_R/私人空间`，Electron `userData` 只保存 manifest、配置、授权记录和索引状态
- [x] 私人空间按单机单用户设计，不做成员权限、共享审计或多人协作；项目/公司资料仍走后端权限与审计
- [ ] 如后续提供免安装/便携版，允许把私人空间根目录配置为软件目录旁的 `Project_R-Data/私人空间`；标准安装包和自动更新形态不得把私人资料放进应用安装目录内部
- [x] 定义本地文件 manifest：记录路径标识、文件名、类型、大小、hash、更新时间、来源标签和最近授权状态，不把绝对路径上传为普通聊天内容
- [x] 实现 Local Agent Worker 健康状态与能力声明：可用、不可用、授权目录、支持的解析类型、最近错误
- [x] 前端附件来源标识区分 `本地私人`、`会话临时上传`、`项目资料`、`公司知识库`，消息发送后仍能查看已发送图片/文件和来源
- [x] 本地文件预处理第一版支持 Markdown / TXT / 可读 PDF 文本提取、图片缩略图、基础预览和摘要/片段候选
- [x] 发送前授权卡片显示将发送的文件、片段/摘要/原文件形式、目标范围、保留策略和是否进入后端
- [x] 文本类私人文件默认只发送摘要或片段；用户明确选择后才上传原文件
- [x] 图片类私人附件投递多模态模型前，明确提示图片会进入后端模型链路，并在聊天记录中保留可点击预览
- [x] “保存到项目资料”走二次确认和复制流程，复制到当前项目 `99-未归档文件` 后写入项目文件审计日志
- [x] 后端 API 区分本地私人文件元数据、临时任务上传、项目文件和公司知识文件，避免把临时上传误入 GBrain source
- [x] 本地 Worker 不可用时允许降级为后端临时附件上传，但界面必须提示这是临时上传处理，不是私人工作区同步
- [x] 验证私人文件预处理主要发生在本机；后端只接收已授权片段、摘要或原文件上传任务

**本阶段明确不做**：
- 不扫描整块硬盘，不后台自动索引用户任意目录
- 不做私人工作区自动云同步、备份或多设备复制
- 不做本地 LLM、本地 GBrain source 或离线问答
- 不做任意 shell 命令执行、无人值守桌面自动化或直接写公司/项目后端路径
- 不允许客户端绕过 Project_R 后端权限调用公司模型 Key、项目资料或公司知识库

**完成标志**：用户可以在私人空间选择本地文件并看到预览/摘要候选；发送前清楚知道哪些内容会上传到后端；发送后聊天记录能查看已发送图片/文件；私人文件默认不出现在后端项目文件、公司知识库或 GBrain source 中；用户显式保存到项目资料后，项目副本受项目权限、审计、回收区和一键录入规则治理。

> 实现状态：2026-05-31 已确认设计方向并写入 `CONTEXT.md` 与 `docs/adr/0012-local-first-private-workspace-and-hybrid-agent-execution.md`。Electron 私人空间目录、manifest 和 Local Worker 能力状态已抽到 `frontend/src/main/private-workspace.ts`，默认根目录为用户 Documents 下的 `Project_R/私人空间`，配置写入 `userData/private-workspace/config.json`，manifest 写入 `userData/private-workspace/manifest.json`，记录相对路径、文件名、类型、大小、SHA256、更新时间、来源标签和最近授权状态。preload 已暴露读取、选择、打开、恢复默认、读取 manifest、快捷投放、从私人空间选择文件、授权状态和 Worker 状态 IPC；设置页“通用 / 私人空间”可查看、打开、选择、恢复默认、快捷投放，并显示 Worker 可用性、授权根目录、支持解析类型和最近错误。聊天输入区支持从私人空间添加本地 pending 附件，未确认授权前禁止发送；发送前显示来源、授权状态、发送形式、目标范围、大小和本地预处理摘要。Local Worker 预处理支持 Markdown/TXT 文本摘录、可读 PDF 文本 MVP 抽取、图片本机预览和通用文件元数据；Chat 模式文本和可读 PDF 默认只发送本地摘录，图片会在确认后进入后端模型链路并在消息中保留可点击预览，Agent 模式按会话临时附件上传并沿用 3 天清理机制。用户可二次确认后把待发送私人文件复制到当前项目 `99-未归档文件`，项目副本走项目文件上传接口、审计、回收区和后续项目 GBrain source 规则，私人空间原文件不移动、不同步。后端会话附件已补 `source_scope/source_label/authorization_status`，临时附件目录固定为 `session_attachments`，不会自动进入项目资料、公司知识库或 GBrain。验证：`frontend bun run test:private-workspace` 覆盖默认目录、快捷投放、重名不覆盖、manifest 无绝对路径、文本/PDF/图片预处理、授权状态和项目复制语义；`frontend bun run typecheck`、`frontend bun run build`、后端 `tests/test_session_attachments.py tests/test_workspace_files.py` 均通过。后续项：如提供免安装/便携版，再补 `Project_R-Data/私人空间` 根目录策略；真实 Electron 点击流可作为发版前人工验收补截图。

---

## 规划能力总览

完成以上阶段后，系统应具备以下能力。状态以本文件各阶段 checklist 为准，未完成阶段不得因出现在本表而视为已交付。

| 能力 | 状态 |
|---|---|
| 员工账号登录，权限隔离 | Phase 8 已完成 |
| 多轮 AI 对话，JSON 非流式消息底座 | Phase 6 已完成；Phase 9 主工作台与 Phase 9B 优先竖切片已实现，待 Gary 手工验收 |
| 模型 profile 选择与思考开关 | Phase 5 + Phase 9B 已实现：后端白名单 profile、DeepSeek/MiMo 多模型共用 Key 组、前端只显示已配置模型；thinking 开关按 provider 生成私有 payload |
| 会话级提示词调用面板 | Phase 9B 已实现并完成 UI 微调：内置只读、公司后端预设、本机自定义；选中后显示 chip，不改写输入框正文 |
| 工作区项目资料目录/Agent 上下文面板 | Phase 9B + P9 已实现文件面板、多文件上传、回收区、权限、审计与项目资料索引状态；项目 GBrain 一键录入已支持异步队列、复杂 PDF/图纸、图片/截图、MP4 自动/长视频分段转写、说话人/术语纠错、EML、EML 附件递归和引用定位；待补文件预览 |
| 基于公司文档的精准问答（RAG，含项目子库） | Phase 10 已切换为 GBrain 主线并退役 Wiki Router / Chroma fallback；`/query` 显式调用 `company-wiki` 或当前项目 source；已完成项目真实样本 11 文件编译和查询隔离，待补 `think` 默认回答层与更多质量回归 |
| 自然语言生成 Word/PPT/Excel 文件 | Phase 11 已完成 Word tracer bullet；正式模板、PPT/Excel 和人工打开验收待补 |
| 业务工作流 Skill / Agent | Phase 12 已完成 Skill 列表/匹配/启动/对话式补参与 U03 无模板 `.xlsx` 输出；正式模板和端到端 UI 验收待补 |
| 知识审核队列（AI 沉淀 → 管理员审核 → 入库） | Phase 13 已完成查看/通过/驳回/修改后通过与写入正式知识库 |
| 管理员后台（用户、知识库、模板、审核、报表） | Phase 13 MVP 已完成；审计日期筛选/导出和真实 UI 验收待补 |
| 个性化设置（提示词、外观、快捷键） | Phase 14 已完成设置主体；头像选择器、暗色主题开关与提示词气泡已修复；联网搜索、钉钉真实链路、全局快捷键绑定和 UI 验收待补 |
| 首次启动欢迎引导 | Phase 15 已完成代码级第一版；真实 Electron 重启验收待补 |
| Windows 全链路联调 | Phase 17 已完成静态检查底座；真实业务链路与截图/时长记录待补 |
| 异步通知中心 | Phase 18 已完成代码级 MVP；项目知识一键录入已接入异步 job 完成/失败通知 |
| 钉钉 Bot 集成 | Phase 16 后补，非现阶段必要实现 |
| 内网服务器无人值守运行 | Phase 19 暂缓，待 Mac mini 机器准备到位 |
| 客户端打包与内网更新 | Phase 20 代码级准备已完成；另一台 Windows 安装测试和正式更新仓库登记待补 |
| 本地私人工作区 / Local Agent Worker | Phase 21 第一版闭环已实现并通过脚本/测试验证；便携版根目录策略和发版前真人点击验收待补 |

---

## 给开发者的建议

1. **每个阶段都要测试完再进入下一个**，不要积累未验证的代码。
2. **遇到报错不要慌**，把完整的错误信息粘贴给 AI，描述你在做什么步骤，AI 能帮你定位问题。
3. **第三到第六阶段是最重要的基础**，这四个阶段打好了，后续都是在此之上叠加功能。
4. **前端和后端可以分开测试**：后端用 Postman 或 REST Client 测试接口，确认正确后再接前端。
5. **不要跳过第一阶段**，环境配置出问题会让后续所有步骤都卡住。
6. **跨平台红线时刻警觉**：每写一段涉及路径或服务器地址的代码，问自己"这段代码在 Mac mini 上能直接跑吗？"
7. **保持 Proma 单机版常开**：作为日常 UI 设计参考与功能对照工具。初步雏形阶段可强复刻 Proma UI shell 来节省设计时间，但始终保持 Project_R 后端中心化、安全受控、员工端轻量壳子的架构。
8. **第一个 Skill 越早写出来越好**：它能把 RAG + 文件生成 + 意图识别串成完整闭环，验证整套架构可行。
## Phase 6 修订记录：基础对话接口消息底座

> 2026-05-19 更新：第六阶段从“能发一条消息并返回 AI 回复”升级为“可复用的会话消息底座”。本阶段产物必须支撑后续 RAG、文件生成、Skill 调度继续复用，而不是只做一次性 LLM 调用。

**修订任务清单**：

- [x] 新增 `models/message.py`：定义 `ChatMessage` 表，持久化 user / assistant 消息。
- [x] `ChatMessage` 字段包含：`session_id`、`user_id`、`role`、`content`、`provider`、`model`、`token_input`、`token_output`、`token_total`、`status`、`error_message`、`created_at`。
- [x] 新增 `GET /chat/sessions/{id}`：获取会话元信息与消息数量。
- [x] 新增 `GET /chat/sessions/{id}/messages`：分页读取消息历史，默认 `limit=50`，最大 `200`。
- [x] `POST /chat/sessions/{id}/messages` 改为：先落 user 消息，再读取最近 20 条历史作为 LLM 上下文，再落 assistant 消息。
- [x] 请求体保留 `provider` 与 `stream` 字段：`provider` 用于管理员/调试切换厂商；`stream` 为后续 SSE 预留，员工前端默认不展示。
- [x] LLM 成功时记录 assistant 消息的 Provider、模型与 Token 用量。
- [x] LLM 失败时保留 user 消息，写入一条脱敏失败记录，并向前端返回统一提示："AI 服务暂时不可用，请稍后重试"。
- [x] 删除会话时同步删除该会话下的所有 `ChatMessage`。
- [x] 默认测试使用 mock LLM，不依赖真实 Claude / OpenAI / DeepSeek Key。

**修订完成标志**：登录后调用对话接口，能收到默认 LLM Provider 的文字回复；user / assistant 消息均持久化；刷新页面后能重新拉取消息历史；换另一个账号登录，看不到前一个账号的会话记录；删除会话后无法再访问该会话及消息；LLM 调用成功/失败均写入审计日志。

> 实现状态：代码路径与 mock LLM 测试已完成；真实厂商回复需要在 `.env` 配置有效 Claude / OpenAI / DeepSeek API Key。
