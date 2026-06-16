# Project_R 开发流程 V2.0

版本：V2.0（产品化精修）
创建时间：2026-06-10
修订时间：2026-06-15
状态：执行计划
规划目标：在已完成的"基座精修"之上，对 Chat、Agent、GBrain 三大板块做针对性产品化精修，把 MVP 推进到"可分发给局部内部人员测试"的水平。

> 本文件是 V2.0 主计划。历史阶段事实（Phase 1-20、GBrain 迁移、9.E 会议 Skill 第一版闭环等）以 `docs/milestones/Project_R 开发流程.md` 为准，本文件不重复。

---

## 0. 修订记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-06-10 | 创建 V2.0（基座精修） | Chat 稳定性 / `/query` 闭环 / 检索 / 基础 Agent 框架四主线 |
| 2026-06-15 | 叠加产品化路线 | 基于代码审计，新增 Chat/Agent/GBrain 三板块产品化清单、Sprint 路线图与逐项验收 |
| 2026-06-15 | 架构优先重排 | 引入"接缝优先 + 反堆叠护栏"，按技术依赖重排执行顺序，新增任务完成定义（DoD）；详见 §3.6 与 §7 |

本次修订对照了 Codex 生成的计划框架（`steady-yawning-phoenix.md`）并逐项核对真实代码，修正了其中的依赖误判（`playwright` 实际不在依赖、`openpyxl` 已存在）、状态误判（多项"未实现"实为"部分实现"），以及一个被忽略的关键约束：`intent.py` 已冻结显式路由，使旧 docx 生成分支成为不可达死代码。

---

## 1. 已完成基线（V2.0 基座精修）

下列基座能力已实现并验证，是本轮产品化的地基，**不在本轮重做**。详细验收记录见 git 历史与下文引用文件。

| 主线 | 已完成内容 | 状态 |
|---|---|---|
| A. Chat 基座 | 标签页/会话/工作区切换不串状态；附件与项目文件引用分离；Markdown/表格/代码块渲染；取消生成与重试；模型选择持久化；提示词三层展示 | 已完成 |
| B. 知识库查询闭环 | `/query` 路径稳定；三类工作区 source scope 隔离（company-wiki / 项目 / 客户）；citation 可点击预览；gap/warning 展示；公司+客户质量回归 | 已完成（项目知识回归待真实 source 闭环） |
| C. 检索与资料发现 | 项目文件搜索与过滤；统一来源预览面板；引用片段定位；按文件类型意图分流排序 | 已完成（独立"知识库检索"面板未做，见 G2） |
| D. 基础 Agent 执行 | Agent 姿态显式切换；补参/计划/确认卡片；Tool 与 Skill 分层；run id/状态/取消/重试；失败写审计与通知 | 已完成（产出文件落地链路未闭环，见 A5） |

> 仍挂起的基座尾项已并入本轮产品化清单：项目知识回归（B 板块沿用旧回归脚本）、知识库独立检索入口（G2）、Agent 产出保存到工作区（A5）、PDF 全面预览（沿用旧 C3）。

---

## 2. 产品化目标与"内测可分发"定义

本轮要回答的核心问题：**普通员工能不能用它替代日常网页版 AI，并信任它的知识库回答和文件产出？**

达到"可分发内测"的最低标准（验收总纲）：

1. **Chat 可日常替代**：流式输出顺滑、草稿不丢、对话可带走（导出），输入与快捷操作符合主流 AI 产品直觉。
2. **Agent 产出可用**：生成结果不只是聊天文本，能落成可下载的标准文件（至少 docx/xlsx/pptx），并能在项目/客户工作区按规则保存。
3. **GBrain 可被普通用户使用**：不需记命令也能浏览/搜索公司知识库，看得到来源与入库状态；管理员能直观看质量与做审核。
4. **技术闸门**：Chat / query / search / agent 四类主路径都有后端测试与前端关键路径测试；不污染真实 `app.db` 与真实 workspace data；`bun run typecheck`、相关 `pytest`、关键 Playwright 通过。

---

## 3. 关键架构约束与已确认决策

本轮所有任务必须遵守以下经代码核实的事实与已拍板决策：

### 3.1 显式路由边界不变（影响 Agent 文档生成）

- `backend/app/features/chat/intent.py` 的 `classify_intent()` 当前**恒返回 `chat`**，且有测试锁定。这导致 `backend/api/chat.py` 内的 docx 生成分支为**不可达死代码**。
- **决策**：本轮**不解冻 intent 自动识别**。文档生成（docx/xlsx/pptx）一律走**显式入口**触发——内置命令 / Skill / Agent 姿态，符合 `AGENTS.md` 的"显式路由优先"与 `docs/adr/0016-explicit-chat-gbrain-routing.md`，无需新 ADR。
- 落地方式：把"文档生成"包装为一个显式可选的内置命令或 Skill（如 `/doc` 或文档生成 Skill），由它调用 `documents/renderer.py` 的渲染器。

### 3.2 业务文件容器规则（影响 A5 保存）

- 个人工作台：Agent/生成产物**只允许本轮展示 + 下载**，不得保存到任何工作区。
- 项目/客户工作区：产物须**用户确认后**才写入当前工作区 `99-未归档文件`（后端 `POST /{workspace_id}/attachments/save` 已存在，默认目录 `DEFAULT_UNFILED_DIR = "99-未归档文件"`），保存不等于自动入库 GBrain。

### 3.3 依赖现状（修正 Codex 误判）

| 依赖 | 真实状态 | 本轮用途 |
|---|---|---|
| `python-docx` | 已在 `requirements.txt` | docx 生成（已可用） |
| `openpyxl` | **已在** `requirements.txt`（当前仅用于预处理读取） | A1 复用其写 xlsx，无需新增依赖 |
| `python-pptx` | **不在**依赖 | A2 需新增 |
| `playwright` | **不在**依赖（Codex 误标"已有"） | A3 PDF 因此降级为后续项，见 3.4 |
| `pypdf` / `PyMuPDF` | 已在依赖 | 仅用于读取/预处理 PDF，非生成 |

### 3.4 PDF 生成本轮降级

- 由于 `playwright` 不在依赖且会引入重型 Node/浏览器依赖，与"可迁移到 Mac mini"红线冲突，**A3 PDF 生成本轮不做**。
- 替代：用户可对生成的 docx/xlsx/pptx 用本地 Office 另存为 PDF；PDF 原生生成留待后续单独评估（docx→pdf headless 转换方案）。

### 3.5 SSE 必须保持 provider 无关

- `backend/app/shared/llm/client.py` 当前用同步 `urllib` 一次性读取响应（`_request_json`）。C1 流式必须在 `LLMClient` 协议 + `BaseProviderClient` 上新增统一的流式方法，由 `AnthropicMessagesClient` 与 `OpenAICompatibleChatClient` 各自实现（两者都加 `stream:true`），**保留 Key 轮询与容错**，业务层不得直接依赖某厂商 SSE 格式。

### 3.6 架构优先执行原则与反堆叠护栏（本轮硬约束）

> 本轮第一目标是"代码框架清晰、可控、可维护"，第二目标才是功能数量。任何任务若以"堆进现有大文件"的方式完成，即使功能可用也视为不合格。通用准则见 `AGENTS.md` / `CLAUDE.md` 的"代码结构与可维护性准则"；本节是其在 V2.0 的具体落地。

**原则一：接缝优先（Seam First）。** 每个板块先建立一个稳定的"接缝"（抽象接口/独立模块），后续功能插入接缝，而不是插入调用点。本轮三个必须先建的接缝：

| 接缝 | 板块 | 内容 | 受益功能 |
|---|---|---|---|
| 流式传输接缝 | Chat | `LLMClient.stream()` 协议 → 后端 `StreamingResponse` → 前端统一 stream reader；建立时把发送/打字机逻辑从 `AppPage.tsx` 抽成 `features/chat/` 内的 hook/service | C1，及后续所有生成体验 |
| 文档产出接缝 | Agent | renderer 注册表（`format → renderer` 映射）+ 显式触发入口 + 统一"生成→（项目/客户区）保存"流程 | A1/A2/A5/B1，新增格式只注册不改调用点 |
| 知识库前端模块接缝 | GBrain | 新建独立 `features/knowledge/` 模块承载浏览/搜索，**不塞进** chat 或 `SettingsModal` | G1/G2/G3/G4 |

**原则二：反堆叠护栏（Anti-God-File）。** 下列文件已严重超出 `AGENTS.md` 体量红线（>800 不堆、>1500 必拆）。本轮**禁止继续增大**它们；相关功能必须先抽离再实现：

| 文件 | 当前行数 | 本轮要求 |
|---|---|---|
| `frontend/src/renderer/pages/AppPage.tsx` | ~2603 | 触碰即抽离：把 chat 发送/流式/草稿/快捷键逻辑拆到 `features/chat/` 的 hooks（如 `useChatSend`、`useChatStream`、`useChatDraft`）。`pages/` 只做组装 |
| `frontend/src/renderer/features/settings/components/SettingsModal.tsx` | ~2291 | 新增管理项（G5/G6/G7）必须落到 `features/admin/`（或 knowledge）子组件，不得继续加进本文件 |
| `backend/api/chat.py` | ~1444 | 保持薄路由：C3 导出、T2 transform、C1 流式的业务逻辑放 `app/features/chat/`，路由只做参数校验与转发 |
| `frontend/src/renderer/features/chat/components/ChatMessageList.tsx` | ~1193 | C4/C8/A5 相关 UI 抽成独立子组件（如 `MessageActions`、`GeneratedFileCard`），不得整体膨胀 |
| `frontend/src/renderer/features/chat/components/AppWorkspaceChrome.tsx` | ~1129 | C9 会话预览等抽成 `SessionListItem` 子组件 |

**原则三：竖切片优先（Vertical Slice）。** 每个板块按"接缝 → 最薄端到端竖切片 → 增强"推进，先让一条真实链路从前端到后端跑通并可验收，再补边缘能力。

**任务完成定义（DoD，每个任务交付必须全部满足）：**

- [ ] 落点正确：功能落在所属 `features/` 或 `app/features/` 模块，未违反目录归属。
- [ ] 未增大上帝文件：触碰上表文件时，净变化以"抽离"为主，不是净增行。
- [ ] 接缝复用：同类新能力（如新文档格式）通过注册/实现接口接入，未复制调用点逻辑。
- [ ] 薄路由：API 层无文件编排/LLM/GBrain/状态机细节。
- [ ] 无死代码：不保留不可达分支（对照 `intent.py` 冻结现状）。
- [ ] provider/vendor 无关：不把某厂商格式泄漏到业务层。
- [ ] 有验证：附后端 `pytest` / `bun run typecheck` / 关键 Playwright，且不污染真实数据。

---

## 4. 板块一：Chat 产品化

目标：让用户能用它替代网页版 ChatGPT/DeepSeek 作为日常入口。执行顺序固定为板块一最先。

### 4.1 清单总览

| # | 功能 | 真实状态 | 优先级 |
|---|---|---|---|
| C1 | SSE 流式输出 | 未实现（前端 `setInterval` 打字机模拟） | P0 |
| C2 | 草稿自动保存 | 未实现（`draft` 仅内存 state） | P0 |
| C3 | 会话导出（Markdown/JSON） | 未实现 | P0 |
| C6 | 输入框自动调整高度 | 未实现（`rows={1}` + 固定高度区间） | P0 |
| C7 | 快捷键真正绑定 | 部分实现（设置页有配置，运行时未绑定） | P1 |
| C4 | 上下文窗口 token 指示器 | 部分实现（后端已存 token，前端无 UI） | P1 |
| C5 | 会话内搜索（当前会话全文） | 未实现（只有跨会话搜索） | P1 |
| C9 | 会话列表预览 | 未实现（侧边栏仅标题+时间） | P2 |
| C8 | 消息引用/回复 | 未实现 | P2 |
| C13 | 模型温度控制 UI | 部分实现（regenerate 支持，发送链路无，无 UI） | P2 |

### 4.2 P0 实现要点与验收

**C1 SSE 流式输出**
- 改动范围：
  - `backend/app/shared/llm/client.py`：`LLMClient` 协议 + `BaseProviderClient` 新增 `stream()`；`AnthropicMessagesClient` 解析 `content_block_delta`，`OpenAICompatibleChatClient` 解析 `choices[].delta.content`；保留 `ProviderKeyPool` 轮询与重试。
  - `backend/api/chat.py`：`send_message` 增加流式分支（消费已有 `SendMessageRequest.stream`），用 `StreamingResponse`（sync generator 跑线程池）逐块输出，末尾发送 token usage 与持久化结果。
  - `frontend/src/renderer/features/chat/api.ts`：新增基于 `fetch` + `ReadableStream.getReader()` 的流式发送，复用现有 `AbortController` 取消机制。
  - `frontend/src/renderer/pages/AppPage.tsx`：用真实增量替换 `typeAssistantReply` 的 `setInterval` 模拟；保留"仅贴底时自动跟随"。
- 验收：后端 `pytest`（mock provider 流式分块）；`bun run typecheck`；Playwright：长回答流式不抖动、可中途取消、取消后可重试、token 写入正确。

**C2 草稿自动保存**
- 改动范围：`AppPage.tsx`（`draft`/`setDraft` 按 `sessionId` 读写 `localStorage`，切换会话回填，发送成功后清空对应 key）；可抽到 `features/chat/state.ts` 工具函数。
- 验收：`bun run typecheck`；手工：输入未发送→刷新/切会话→回到原会话草稿恢复，发送后清空。

**C3 会话导出**
- 改动范围：`backend/api/chat.py` 新增 `GET /chat/sessions/{id}/export?format=markdown|json`（薄路由，组装逻辑放 `app/features/chat/`）；`frontend/src/renderer/features/chat/api.ts` + 会话菜单加导出按钮。
- 验收：后端 `pytest`（导出含全部消息、角色、时间、引用；权限校验非本人会话拒绝）；`bun run typecheck`；手工下载校验。

**C6 输入框自动调整高度**
- 改动范围：`frontend/src/renderer/features/chat/components/ChatComposer.tsx`（textarea 监听 `scrollHeight` 动态调高）；`frontend/src/renderer/shared/styles/global.css`（`.composer textarea` min/max-height 配合）。
- 验收：`bun run typecheck`；手工：多行输入自动增高至上限后内部滚动，发送后回落。

### 4.3 P1/P2 实现要点

| # | 改动范围 | 验收 |
|---|---|---|
| C7 | `AppPage.tsx` 全局 `keydown` 读取 `preferences.shortcuts`（`SettingsModal` 已存 `DEFAULT_SHORTCUTS`），绑定 Ctrl+K(搜索)/Ctrl+N(新会话)等 | 手工逐快捷键验证 + 与设置页一致 |
| C4 | `ChatMessageList.tsx` 输入区显示"已用 X / 上限 tokens"，数据取自 message 的 `token_total` | `bun run typecheck` + 手工核对 |
| C5 | 当前会话消息列表内全文搜索（前端过滤/高亮，复用 `SearchDialog` 样式但限定当前会话） | `bun run typecheck` + Playwright 高亮命中 |
| C9 | 后端 `list_sessions` 附最后一条消息摘要；`AppWorkspaceChrome.tsx` 会话项展示预览 | 后端 `pytest` + 手工 |
| C8 | `ChatMessageList.tsx` 消息操作加"引用"，Composer 加 quoted 字段 | `bun run typecheck` + 手工 |
| C13 | `SendMessageRequest` 加 `temperature`；`ChatComposer.tsx` 加温度滑块；`api/chat.py` 透传 | 后端 `pytest` + 手工 |

---

## 5. 板块二：Agent 效率工具

目标：Agent 产出从"聊天文本"变为"可用文件"，并能按规则落到工作区。执行顺序在 Chat 之后。

### 5.1 清单总览

| # | 功能 | 真实状态 | 优先级 |
|---|---|---|---|
| A1 | Excel(xlsx) 生成 | 未实现（仅 docx 渲染器，`openpyxl` 已具备） | P0 |
| A2 | PPT(pptx) 生成 | 未实现（`python-pptx` 需新增；frontend-slides 产 HTML 非 pptx） | P0 |
| A5 | 产出保存到工作区 `99-未归档文件` | 部分实现（后端 API 已存在，前端 `saveAttachmentToWorkspace` 定义未调用） | P0 |
| 触发 | 文档生成显式入口（命令/Skill） | 未实现（docx 分支因 intent 冻结不可达） | P0 |
| B1 | `.eml` 文件生成 | 未实现 | P1 |
| B2 | `mailto:` 启动邮件客户端 | 未实现 | P1 |
| B3 | 自动复制草稿到剪贴板 | 部分实现（有手动复制，无自动） | P1 |
| T2 | `POST /chat/transform` 文本变换端点 | 未实现 | P1 |
| T1 | 改写/翻译/总结一键按钮 | 未实现 | P2 |
| A3 | PDF 生成 | 未实现 | 后续（见 3.4） |
| A4 | tag-printing Skill | 不存在于代码库（Codex 误标在 `_release/`） | 后续/待确认需求 |

### 5.2 P0 实现要点与验收

**文档生成显式入口（前置，A1/A2 依赖它）**
- 改动范围：新增显式内置命令或 Skill（如 `/doc`），路由到 `backend/app/features/chat/document_generation.py`；不改 `intent.py`。前端在 `slashCommands.ts` 注册。
- 验收：后端 `pytest`（显式命令触发生成；普通 chat 不触发）；`bun run typecheck`。

**A1 Excel 生成 / A2 PPT 生成**
- 改动范围：
  - `backend/app/features/documents/renderer.py`：新增 `render_xlsx`（`openpyxl`，把 Markdown 表格→工作表）、`render_pptx`（`python-pptx`，标题/要点→幻灯片）。
  - `backend/app/features/chat/document_generation.py`：`create_generated_*` 支持按目标格式落 `GeneratedFile` 与 MIME。
  - `backend/requirements.txt`：新增 `python-pptx`（固定版本）。
- 验收：后端 `pytest`（生成文件可被 openpyxl/python-pptx 反读校验内容）；产物落在隔离的 `generated_files/`，不污染真实数据。

**A5 产出保存到工作区**
- 改动范围：`frontend/src/renderer/features/chat/components/ChatMessageList.tsx` 的 `renderGeneratedFileCard` 在**项目/客户工作区**增加"保存到工作区"按钮，调用已存在的 `saveAttachmentToWorkspace`→`POST /{workspace_id}/attachments/save`；个人工作台**只显示下载**。
- 验收：后端 `pytest`（保存到 `99-未归档文件`、权限边界、个人工作台拒绝跨区保存）；Playwright：项目区可保存、个人区无保存入口。

### 5.3 P1/P2 实现要点

| # | 改动范围 | 验收 |
|---|---|---|
| B1 | 后端用标准库 `email`/`email.policy` 生成 `.eml` → `GeneratedFile`；前端结果卡片加"下载 .eml" | 后端 `pytest`（.eml 可被邮件客户端解析头/正文） |
| B2 | 前端结果卡片生成 `mailto:` 链接并由主进程/默认客户端打开 | 手工：点击拉起本地邮件客户端 |
| B3 | 邮件草稿 Skill 结果卡片加"复制到剪贴板"（含自动复制可选项） | `bun run typecheck` + 手工 |
| T2 | `backend/api/chat.py` 新增薄路由 `POST /chat/transform`（text+action: rewrite/translate/summarize/expand），逻辑放 `app/features/chat/` | 后端 `pytest` 四类 action |
| T1 | 工具栏/选中文本浮动按钮，调用 T2；结果可替换或作为新消息 | `bun run typecheck` + Playwright |

---

## 6. 板块三：GBrain 产品化

目标：普通用户不记命令也能用知识库；管理员能直观维护。执行顺序最后（放大前两板块的稳定性收益）。

### 6.1 清单总览

| # | 功能 | 真实状态 | 优先级 |
|---|---|---|---|
| G1 | 知识库浏览 UI（公司知识目录/分类） | 未实现（仅 `/query` 命令；项目图谱另算） | P0 |
| G2 | 知识库搜索独立入口 | 未实现（依赖 `/query` 对话式） | P0 |
| G3 | 搜索结果过滤（source/类型/时间） | 未实现（用户侧 UI） | P1 |
| G4 | Source 状态用户可见 | 部分实现（文件级 `rag_status` 成员可见） | P1 |
| G5 | 质量报告可视化 | 部分实现（管理员文字摘要+JSON 导出，无图表） | P1 |
| G6 | 知识审核增强（diff + 批量） | 部分实现（单条通过/驳回，无 diff/批量） | P1 |
| G7 | GBrain 状态仪表板 | 部分实现（指标卡片+文字趋势，无趋势图） | P2 |

### 6.2 P0 实现要点与验收

**G1 知识库浏览 UI / G2 搜索独立入口**
- 改动范围：新增前端 feature（`frontend/src/renderer/features/knowledge/...`）——独立面板：公司知识目录浏览 + 搜索框（区别于 Chat 的 `/query`）。后端复用现有 GBrain 查询/source 接口（`backend/api/rag.py`、`app/features/knowledge/`），必要时补只读列表端点（薄路由）。
- source scope 严格遵守 GBrain 边界：个人工作台只 `company-wiki`；项目区 `company-wiki + 当前项目`；客户区只客户情报。
- 验收：后端 `pytest`（三类 source scope 列表/搜索）；`bun run typecheck`；Playwright：浏览→搜索→点击→来源预览/发起 `/query`；普通 Chat 不被升级为知识库检索。

### 6.3 P1/P2 实现要点

| # | 改动范围 | 验收 |
|---|---|---|
| G3 | 搜索面板加 source/类型/时间过滤控件（后端排序权重已有，补用户可选过滤） | 后端 `pytest` + Playwright 过滤/空结果 |
| G4 | 把文件级 `rag_status` 可见性扩展为更清晰的 source 状态提示（沿用 `WorkspaceFileRow` 徽章） | `bun run typecheck` + 手工 |
| G5 | `AdminSettingsPanel.tsx` 质量报告区加图表组件（通过率趋势、失败分布），数据取自 `GET /quality/reports` | `bun run typecheck` + 手工 |
| G6 | 审核 tab 加 side-by-side diff（原答案 vs 修正）与批量通过/驳回（后端补 batch 端点） | 后端 `pytest` + 手工 |
| G7 | GBrain 概览区把文字趋势升级为趋势图（健康分/jobs/contradictions） | `bun run typecheck` + 手工 |

---

## 7. Sprint 执行路线图（架构优先重排）

### 7.1 优先级排序依据

任务顺序不再单纯按"感知提升"排，而是按以下权重综合排序（高到低）：

1. **是否解锁后续工作（接缝）**：先做被多项依赖的接缝，避免反复返工。
2. **技术风险**：高风险/未知项尽早试错（如 C1 流式贯穿前后端）。
3. **用户感知价值**。
4. **成本**。

由此对 Codex 原排序的两点修正：①每个板块的**首个 Sprint 强制以"接缝 + 抽离上帝文件"开头**，功能竖切片随后；②文档产出板块把"显式触发入口 + renderer 注册表"提为最高前置（A1/A2/A5/B1 都依赖它），而非与格式实现并列。

板块大顺序仍固定 **Chat → Agent → GBrain**（串行承诺）。

### 7.2 路线图

```
板块一 · Chat
Sprint 1  流式接缝 + 抽离（架构地基，P0）【Codex接管】
├── S1.1 建立流式传输接缝：LLMClient.stream() / 后端 StreamingResponse / 前端 stream reader【Codex接管】
├── S1.2 抽离：把 AppPage.tsx 发送+打字机逻辑迁出为 features/chat/ hooks（useChatStream/useChatSend）【Codex接管】
└── S1.3 C1 竖切片：一条真实流式链路端到端跑通、可取消、可重试、token 正确【Codex接管】

Sprint 2  Chat 核心痛点（P0）
├── C2 草稿自动保存（落 features/chat/，useChatDraft）
├── C6 输入框自动调整高度（ChatComposer）
└── C3 会话导出（薄路由 + app/features/chat/ 导出服务）【Codex审核】

Sprint 3  Chat 体验增强（P1/P2）
├── C7 快捷键绑定（全局 hook 读 preferences.shortcuts）
├── C4 token 指示器 / C5 会话内搜索
└── C9 会话预览（抽 SessionListItem）/ C8 引用 / C13 温度

板块二 · Agent
Sprint 4  文档产出接缝（架构地基，P0）【Codex接管】
├── S4.1 显式触发入口（命令/Skill，不解冻 intent）【Codex接管】
├── S4.2 renderer 注册表：format→renderer 映射，docx 先接入注册表【Codex接管】
└── S4.3 统一"生成→保存"流程接缝（含个人/项目/客户区规则）【Codex接管】

Sprint 5  Agent 文件格式与落地（P0）
├── A1 Excel 生成 / A2 PPT 生成（注册进 renderer，+ python-pptx 依赖）
└── A5 产出保存到工作区（接 saveAttachmentToWorkspace，区分工作区）【Codex审核】

Sprint 6  Agent 邮件与文本变换（P1/P2）
├── B1 .eml（作为一个 exporter 接入产出接缝）/ B2 mailto / B3 剪贴板
├── T2 transform 端点（薄路由 + app/features/chat/ 服务）【Codex审核】
└── T1 一键变换按钮（调用 T2）

板块三 · GBrain
Sprint 7  知识库前端模块接缝（架构地基，P0）【Codex接管】
├── S7.1 新建 features/knowledge/ 模块骨架（不塞进 chat / SettingsModal）【Codex接管】
├── S7.2 后端按需补只读列表端点（薄路由，复用现有 GBrain 接口）【Codex接管】
└── S7.3 G1 浏览 + G2 搜索竖切片（严格 source scope）【Codex接管】

Sprint 8  GBrain 用户侧增强（P1）
├── G3 结果过滤
└── G4 Source 状态用户可见

Sprint 9  GBrain 管理侧（P1/P2）
├── G5 质量报告可视化（落 features/admin/ 子组件，不进 SettingsModal）
├── G6 审核增强（diff + 批量）【Codex审核】
└── G7 状态仪表板
```

### 7.3 每个 Sprint 的完成闸门

- 清单内 P0 项全部实现并通过 §3.6 的 DoD（含"未增大上帝文件"）。
- 通过对应验收闸门（`pytest` / `bun run typecheck` / 关键 Playwright）。
- "架构地基"型 Sprint（S1/S4/S7）额外要求：接缝接口稳定、至少一条竖切片复用该接缝、相关上帝文件**净行数下降或持平**。
- 未验证项保持未勾选，不得提前勾 checklist。

---

## 8. 依赖与环境变更

| 依赖/变更 | 板块 | 动作 |
|---|---|---|
| `python-pptx` | A2 | 新增到 `backend/requirements.txt`（固定版本） |
| `openpyxl` | A1 | 已存在，复用，无需新增 |
| `python-docx` | docx | 已存在 |
| `email`/`email.policy`（标准库） | B1 | 无需新增 |
| `SendMessageRequest.stream` | C1 | 已存在字段，本轮接通消费逻辑 |
| `.env.example` | 全 | 若新增可配置项（如流式开关）须同步示例，真实 `.env`/Key 不入库 |

> 安装依赖前需获授权；安装后跑相关 `pytest` 确认无回归。

---

## 9. V2.0 明确不做项

- 普通 Chat 自动查 GBrain / 自动识别文档意图（保持显式路由）。
- A3 PDF 原生生成（本轮降级，见 3.4）。
- 新增大批业务 Skill；复杂会议深水区；客户情报自动运营。
- 个人工作台文件库、个人 GBrain source、个人长期记忆。
- 用 Project_R 自建替代 GBrain 的图谱/timeline/citation/embedding。
- 完整 MCP 协议支持、语音实时麦克风（C11）、批量会话操作（C12）、回复长度预设（C14）——按需后补。

---

## 10. 第一批可执行任务建议

1. **建流式接缝（后端）**：在 `llm/client.py` 加 `stream()`（provider 无关、保留 Key 轮询），用 mock provider 写流式 `pytest`，再接 `api/chat.py` 的 `StreamingResponse`（业务逻辑放 `app/features/chat/`）。
2. **抽离 + 前端接流**：先把 `AppPage.tsx` 的发送/打字机逻辑迁出为 `features/chat/` 的 `useChatStream`/`useChatSend`，再用 `ReadableStream` 读取真实增量，复用现有取消机制。此步要求 `AppPage.tsx` 净行数下降。
3. **C2 草稿持久化**：新增 `features/chat/` 的 `useChatDraft`，按 sessionId 读写 `localStorage`，不要把逻辑堆回 `AppPage.tsx`。
4. **文档产出接缝**：在 `documents/renderer.py` 建 `format→renderer` 注册表并把 docx 接入；在 `slashCommands.ts` + `document_generation.py` 打通显式触发（保持 `intent.py` 不变），为 A1/A2 铺路。
5. **A5 保存流程接缝**：把"生成→保存"做成可复用流程，前端在 `ChatMessageList.tsx` 抽 `GeneratedFileCard` 子组件接 `saveAttachmentToWorkspace`，区分个人/项目工作区。

---

## 11. 验收总标准

### 11.1 用户体验
- 普通员工可流式聊天、草稿不丢、导出对话、用快捷键操作。
- Agent 产出能落成 docx/xlsx/pptx 并按规则保存到项目/客户工作区。
- 用户能浏览/搜索公司知识库并看到来源与入库状态。
- 始终能区分"普通 Chat / 查知识库 / 执行 Agent"三种状态。

### 11.2 技术
- Chat / query / search / agent 四类主路径有后端测试 + 前端关键路径测试。
- SSE 保持 provider 无关、Key 轮询与容错；流式可取消可重试。
- 不污染真实 `backend/app.db` 与真实 workspace data。
- `bun run typecheck`、相关 `pytest`、关键 Playwright 通过；涉及 source scope 改动跑 query/source scope 回归。

### 11.3 文档
- 本文件是 V2.0 主计划；`Project_R 开发流程.md` 保留历史事实。
- 若改 Chat / GBrain 边界，必须同步 `CONTEXT.md` 与 ADR；本轮不改该边界。
- 若改前端视觉语言，必须先看并同步 `docs/design/ui-design-language.md`。
- 新增/修改业务 Skill 后同步 `docs/product/Project_R 业务工作流清单.md`。
