# Sprint 8 GBrain Evidence UX 验收记录

日期：2026-06-17

## 1. 目标

Sprint 8 采用方案 1.5：为普通用户增强“本轮回答证据解释体验”，而不是做知识库浏览器。

用户应能判断：

- 本轮回答引用了哪些来源。
- 来源属于公司知识、项目资料、客户情报、外部来源还是授权来源。
- 来源能否定位到页码、行号、locator 或仅能文件级定位。
- 本轮是否存在 gap / conflict / warning。
- 筛选仅影响本轮引用来源展示，不浏览完整知识库。

## 2. 实现范围

- 新增 `frontend/src/renderer/features/knowledge/sourceEvidence.ts` 与 `sourceEvidenceTypes.ts`，作为前端 evidence normalization 层。
- 新增 `SourceEvidenceFilters`、`SourceEvidenceSummary`、`SourceEvidencePanel`。
- `MessageSourceList` 支持本轮来源筛选和空状态。
- `SourcePreviewPanel` 显示证据说明、定位、限制和风险提示。
- `ChatMessageList` 只做薄接线，把 `context_trace` 传入来源组件。

## 3. 不做项

- 不做普通用户知识库浏览器。
- 不请求全量 source。
- 不展示 chunk、raw rag_status、embedding status、后台质量报告。
- 不做管理员 source 管理列表。
- 不做伪精确可信度评分。

## 4. 代码级验收

- [x] `MessageSourceList` 只接收并筛选当前消息的 `message.sources`，没有请求全量 source。
- [x] `visibleEvidenceFilters` 只在当前回答存在对应类型时显示筛选 chips。
- [x] `filterSourceEvidences` 的公司知识 / 项目资料 / 客户情报 / 外部来源筛选只作用于本轮 evidence 列表。
- [x] 无对应来源时显示“本轮回答未引用该类来源”的空状态。
- [x] `SourceEvidenceSummary` 显示本轮引用数量、来源范围、定位有限和风险提示数量。
- [x] `SourceEvidencePanel` 显示证据说明、来源范围、定位、限制说明和 gap / conflict / warning。
- [x] 普通用户侧没有新增全量 source、知识库目录、入库状态列表或管理员 source 管理入口。

## 5. 手工 UI 验收清单

Computer Use 在本机初始化失败，无法替代人工完成界面点击验收。本轮需要手工确认以下 UI 行为：

- [ ] 有多个来源类型时，来源区显示筛选 chips。
- [ ] 点击公司知识 / 项目资料 / 客户情报 / 外部来源 / 需核对筛选时，列表只变化本轮引用来源。
- [ ] 选择无对应来源的筛选项时，显示“本轮回答未引用该类来源”的空状态。
- [ ] 来源摘要显示本轮引用数量、来源范围、定位有限和风险提示数量。
- [ ] 点击来源后，右侧预览显示证据说明、来源范围、定位和限制说明。
- [ ] 有 `context_trace.gbrain_think.gaps/conflicts/warnings` 时，来源列表可筛选“需核对”，右侧预览显示风险详情。
- [ ] 普通用户仍看不到全量 source / 知识库目录 / 入库状态列表。

## 6. 验证

- `cd frontend && bun run typecheck`
- `git diff --check`
- Computer Use 初始化失败：本地插件脚本依赖 `@oai/sky` 子路径导出异常，未能进入应用窗口枚举。
- 如后续补稳定 mock 场景，再增加 Playwright 覆盖本轮筛选和风险提示。

## 7. Sprint 8.2 来源证据可读性修正

### 7.1 修正范围

- 后端新增 best-effort evidence enrichment：`evidence_excerpt`、`display_title`、`original_source_file`、`locator_label`、`metadata_only`。
- 每条 citation 按自身 source scope 选择读取路径：company 只读 company derived；project 只读当前 project workspace derived；customer/crm 只读当前 customer workspace derived；unknown 不读取。
- 禁止把 GBrain citation metadata 写入 `content` 并伪装为引用片段；解析不到原文时返回 `metadata_only=true`。
- 前端来源面板优先显示用户可读 evidence excerpt；无 excerpt 时显示“当前 GBrain 仅返回引用坐标，未返回可展示的原文片段。”
- 技术详情（source slug / page slug / row）默认折叠；gap / conflict / warning 放在证据之后。

### 7.2 后端验证

- [x] 有 excerpt：可从授权 company/project root 解析并返回可读片段。
- [x] 无 excerpt：返回 `metadata_only=true`，且 `content` 不伪装 metadata。
- [x] project workspace 内 company citation 和 project citation 分别从各自 root 读取。
- [x] company/project/customer 不互相 fallback。
- [x] 跨 workspace project source 不读取。
- [x] 多候选 original file stem 返回 `metadata_only=true`。
- [x] `original_source_file` 不暴露本地绝对路径。
- [x] enrichment 异常不阻塞 GBrain think 回答生成。

### 7.3 验证命令

- `cd backend && .\venv\Scripts\python.exe -m pytest tests/test_knowledge_evidence.py`
- `cd frontend && bun run typecheck`
- `git diff --check`

## 8. 阶段判断

Sprint 8.1 已认定为代码级闭环但产品级 UI 验收未通过。Sprint 8.2 已完成来源证据可读性代码修正：来源面板不再把技术坐标当引用片段，能在可解析时展示 evidence excerpt，无法解析时明确降级。筛选功能仍保持代码级验证，待公司知识库、项目信息和 CRM 信息补齐后再做产品级筛选验收。
