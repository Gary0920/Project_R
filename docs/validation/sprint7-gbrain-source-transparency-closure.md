# Sprint 7 GBrain 来源透明与管理员知识入口闭环验收

日期：2026-06-17

## 1. 验收结论

Sprint 7 可视为阶段性闭环，达到可进入 Sprint 8 的产品交付水准。

本轮闭环覆盖的是 P0 架构地基与用户可信查询体验：普通用户能在知识库查询前理解本次 source scope，查询后能查看本轮引用片段与定位；管理员能进入知识概览入口查看 GBrain / company-wiki / 质量报告摘要与维护动作。普通用户仍不能枚举全量 source、文件目录、chunk、入库状态或质量报告。

G3-G7 不纳入 Sprint 7 完成口径，按原计划进入 Sprint 8 / Sprint 9。

## 2. 市场成熟产品对照

参考成熟知识问答产品的共同设计方向：

- Google NotebookLM 的 source-first 体验：用户先管理/选择 sources，再围绕 sources 提问，回答以来源材料为可信边界。
- Microsoft Copilot / Copilot Studio 的企业权限模型：SharePoint 等知识源会按用户身份和权限使用，用户不能越权获得未授权内容。
- Perplexity / 搜索型 AI 的可验证引用体验：回答应提供可追踪来源，用户能回看证据，而不是只得到模型结论。

Project_R Sprint 7 的落地判断：

- 符合：普通用户侧以“来源范围提示 + 本轮引用片段预览”建立信任，不做普通用户知识库浏览器。
- 符合：管理员治理能力与普通用户问答体验分离，知识元数据进入管理员入口。
- 符合：引用展示只显示本轮回答实际使用片段，减少内部知识库原文被浏览或枚举的风险。
- 待后续增强：G3 结果过滤、G4 source 状态解释、G5-G7 管理图表与审核效率提升。

参考来源：

- Google NotebookLM Help: Add or discover new sources for your notebook, https://support.google.com/notebooklm/answer/16215270
- Microsoft Copilot Studio: Knowledge sources summary, https://learn.microsoft.com/en-us/microsoft-copilot-studio/knowledge-copilot-studio
- Microsoft Copilot Studio: Add SharePoint as a knowledge source, https://learn.microsoft.com/en-us/microsoft-copilot-studio/knowledge-add-sharepoint

## 3. 用户操作逻辑验收

### 普通用户

通过标准：

- 在输入 `/query` 或选择等价知识库查询命令时，输入框附近显示本次将查询的范围和不会查询的范围。
- 个人工作台只提示公司知识；项目工作区提示公司知识 + 当前项目资料；客户工作区只提示当前客户情报。
- AI 回复底部显示引用来源列表，来源项包含来源范围、标题或定位信息。
- 点击来源项后，右侧只显示本轮引用片段、标题、必要路径和定位说明。
- UI 不提供普通用户浏览完整知识库文件、全量 source 列表、chunk、入库状态、质量报告的入口。
- 普通 Chat 不自动升级为 GBrain 检索；仍需显式 `/query` 或知识库入口。

结论：通过代码实现与边界检查。需要 Electron 手工验收时，可按以上 6 项逐项点检。

### 管理员

通过标准：

- 管理员设置中的知识入口可查看 GBrain 服务状态、source 注册、语义检索、页面/片段、嵌入模型、最近编译、doctor 分数。
- 管理员可查看 readiness errors、doctor warning / failed checks。
- 管理员可查看最近质量报告、失败用例、预检失败和最近趋势摘要。
- 管理员可触发已有操作：查询质量报告、Think 质量报告、导出报告、启动/重启 GBrain、导入 raw 并同步、含 PDF 提炼。
- 管理员知识概览已拆到 `frontend/src/renderer/features/admin/knowledge/`，不继续堆进 `AdminSettingsPanel.tsx`。

结论：通过代码实现与类型检查。图表化、批量审核、source 状态深治理按 Sprint 9 处理。

## 4. 安全边界验收

通过标准：

- 未新增普通用户知识库浏览器。
- 未暴露全量 source 列表、目录、chunk、入库状态、质量报告。
- 未修改 GBrain 原生代码或 `reference/gbrain-master`。
- 未新增绕过 Project_R 权限判断的前端直连 GBrain 入口。
- 管理员入口复用现有 Project_R admin API。

结论：通过。

## 5. 结构与维护性验收

通过标准：

- 普通用户来源透明模块落在 `frontend/src/renderer/features/knowledge/`。
- 管理员知识概览模块落在 `frontend/src/renderer/features/admin/knowledge/`。
- 消息 Markdown 渲染接缝抽到 `frontend/src/renderer/features/chat/messageContent.tsx`，避免来源预览反向依赖 `ChatMessageList.tsx`。
- `ChatMessageList.tsx` 与 `AdminSettingsPanel.tsx` 净行数下降，但仍超过 800 行，后续全局结构治理时继续拆。
- 本轮未新增后端大文件，也未向 `AppPage.tsx` 继续堆管理逻辑。

结论：通过 Sprint 7 结构门槛；大文件治理不阻塞 Sprint 7，但保留为后续架构治理项。

## 6. 已执行验证

- `cd frontend && bun run typecheck`：通过。
- `git diff --check`：通过，仅出现 Windows 换行提示。
- 后端 pytest：未运行。本轮收尾没有后端代码改动。

## 7. 剩余事项归属

- Sprint 8：G3 查询结果过滤与来源类型提示。
- Sprint 8：G4 普通用户侧 source 状态解释与管理员 source 状态增强。
- Sprint 9：G5 质量报告图表化。
- Sprint 9：G6 知识审核 diff + 批量处理。
- Sprint 9：G7 GBrain 状态仪表板图表化。

## 8. 阶段判断

Sprint 7 的 P0 目标已经完成：Project_R 具备知识库查询的来源透明体验和管理员知识概览入口，且保持普通用户数据泄露边界。功能达到阶段性交付水平，可进入 Sprint 8。
