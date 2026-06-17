# Sprint 9.1 / G6.0 知识审核工作台验证记录

日期：2026-06-17

## 范围

G6.0 是前端审核工作台 MVP，不等于完整 G6。

本轮完成：
- 从 `AdminSettingsPanel.tsx` 抽离知识审核 UI。
- 新增 `frontend/src/renderer/features/admin/knowledge/reviews/`。
- 提供审核列表、单条详情、原内容 vs 本地编辑草稿并排对比。
- 保留单条通过、驳回、citation-fixer。
- 增加当前页已选项的安全批量通过 / 批量驳回。

本轮不做：
- 后端 batch endpoint。
- 审核备注持久化。
- 审核历史记录。
- 风险标签系统。
- G7 dashboard。
- 大型 diff viewer。

## 后端行为确认

已确认 `POST /admin/knowledge-reviews/{review_id}` 支持提交修改内容：

- 请求模型 `ReviewKnowledgeRequest` 含 `content: str | None`。
- 路由在审核前执行 `review.content = req.content.strip()`。
- 通过时再调用现有写入 GBrain 的审批逻辑。
- 后端已有测试 `test_approve_review_can_modify_content_and_does_not_duplicate_sink` 覆盖修改内容后通过。

因此 G6.0 UI 可以在单条通过时提交右侧 proposed content。

## 批量操作边界

批量操作是前端串行调用现有单条审核接口，后端 batch endpoint 后置。

批量通过只允许：
- 当前可见页已选项；
- `status === "pending"`；
- 本地草稿未编辑；
- 非 citation-fixer 可处理项。

批量驳回只允许：
- 当前可见页已选项；
- `status === "pending"`。

搜索条件变化或分页切换会清空选择，不做跨页批量选择。

批量结果必须展示：
- 成功数；
- 失败数；
- 跳过数；
- 失败项 id/source；
- 跳过项 id/source/reason。

## 验收项

- `AdminSettingsPanel.tsx` 不再保留 reviews tab 的业务渲染主体。
- reviews 模块落在 `features/admin/knowledge/reviews/`。
- 可以查看审核列表和单条详情。
- 可以左右对比原 content 和 proposed content。
- 单条通过 / 驳回可用。
- 编辑草稿后只能单条通过，不能批量通过。
- 批量通过 / 驳回有二次确认、执行中禁用和完整结果反馈。
- citation-fixer 保留单条入口。
- `bun run typecheck` 通过。

## G6.0 手工验收补录

结论：G6.0 记为“前端审核工作台 MVP 通过”，不标记完整 G6 完成。

说明：本轮尝试使用 Windows 自动化代替人工点击验收，但 Computer Use 运行时初始化失败：

```text
Package subpath './dist/project/cua/sky_js/src/targets/windows/internal/computer_use_client_base.js' is not defined by "exports" in ...\@oai\sky\package.json
```

因此以下记录采用代码路径核对 + 可复现内联样例验证，不伪装为真实桌面 UI 点击结果。后续如 Project_R 桌面端已运行且 Computer Use 恢复，可按同一清单复验。

### 浏览器补验

用户追问后，改用浏览器打开当前已运行的前端地址验证：

- 前端地址：`http://127.0.0.1:5174/`
- 登录账号：`sysadmin / Admin123`
- 登录结果：通过，进入 `/#/app`
- 管理员后台：可进入
- 知识审核页：可进入
- 当前真实待审核数据：`0 条匹配`

浏览器可见状态：

```text
heading "知识审核"
paragraph "G6.0 审核工作台 MVP：本地草稿对比、单条审核和当前页安全批量操作。"
textbox "搜索 id、来源或内容"
generic "0 条匹配"
generic "可批量通过 0 条 · 可批量驳回 0 条"
button "批量通过" [disabled]
button "批量驳回" [disabled]
paragraph "当前页没有待审核知识。"
```

限制说明：当前真实环境没有 pending review。按真实数据隔离规则，本轮未直接向真实 `app.db` 写入临时 `KnowledgeReview` 记录；用户提到可创建临时文件，但临时文件本身不能稳定生成审核队列数据。因此列表详情、单条提交、批量半失败等交互仍以代码路径 + 内联样例验证为准，未伪装为真实浏览器点击通过。

| # | 验收项 | 结果 | 依据 |
|---|---|---|---|
| 1 | 管理侧知识审核入口可进入 | 通过（浏览器 + 代码路径） | 浏览器已进入管理员后台并切换到“知识审核”；`AdminSettingsPanel.tsx` 在 `adminTab === "reviews"` 时挂载 `KnowledgeReviewPanel`。 |
| 2 | 列表、搜索、分页正常 | 部分通过（浏览器空状态 + 样例） | 浏览器显示 `0 条匹配` 空状态；`filterKnowledgeReviews` 样例返回匹配项；真实分页因无数据未点击验证。 |
| 3 | 搜索或分页变化会清空选择 | 通过（代码路径） | `KnowledgeReviewPanel` 的 `useEffect([reviewSearch, safePage])` 清空 `selectedIds` 和批量结果。 |
| 4 | 单条详情显示原 content 和 proposed content | 通过（代码路径） | `KnowledgeReviewDetail` 左侧 `pre` 渲染 `item.content`，右侧 `textarea` 渲染 draft。 |
| 5 | proposed content 修改后提示正确 | 通过（样例） | `buildReviewDiffSummary("原内容", "修改后内容")` 返回 `changed=true` 和修改摘要。 |
| 6 | 编辑过的 review 不能被批量通过 | 通过（样例） | `canBatchApprove(edited, drafts)` 返回 `false`，跳过原因是“已有本地编辑草稿，只能单条审核”。 |
| 7 | 单条通过能提交 proposed content | 通过（代码路径 + 后端确认） | 后端 `ReviewKnowledgeRequest.content` 会写回 `review.content`；前端单条通过传入 draft。 |
| 8 | 单条驳回不提交 proposed content | 通过（代码路径） | `KnowledgeReviewDetail` 驳回调用不传 content；`SettingsModal` 仅 approved 时转发 content。 |
| 9 | citation-fixer 单条入口保留 | 通过（代码路径） | `KnowledgeReviewDetail` 对 `canSubmitCitationFixer(item)` 显示“引用修复”。 |
| 10 | 批量通过/驳回只作用当前可见页已选项 | 通过（代码路径；浏览器确认空状态按钮禁用） | `selectedItems = visibleItems.filter(...)`，批量只遍历 `selectedItems`；无数据时批量按钮禁用。 |
| 11 | 批量结果显示成功/失败/跳过项 | 通过（代码路径） | `KnowledgeReviewBulkBar` 展示 success/failed/skipped 数量，并列出 failed/skipped id/source/reason。 |
| 12 | 刷新后状态正确更新 | 通过（代码路径） | `handleReviewKnowledge` 成功后调用 `loadAdminData()`；批量串行复用该 handler。 |
| 13 | `AdminSettingsPanel.tsx` 不再承载 reviews tab 主体逻辑 | 通过（代码路径） | reviews tab 只挂载 `KnowledgeReviewPanel` 并转发 props；上一轮 diff 显示该文件净减少审核 UI 逻辑。 |

## 自动验证

已执行：

```powershell
cd frontend
bun run typecheck
```

结果：通过。

已执行内联样例：

```powershell
cd frontend
bun --eval "import { canBatchApprove, canBatchReject, batchSkipReason, filterKnowledgeReviews } from './src/renderer/features/admin/knowledge/reviews/knowledgeReviewView.ts'; ..."
```

结果：通过。
- 普通 pending 项可批量通过 / 批量驳回。
- 已编辑草稿项不可批量通过，原因显示“已有本地编辑草稿，只能单条审核”。
- citation-fixer 项不可批量通过，原因显示“citation-fixer 状态不明，只能单条审核”。

补充执行：

```powershell
cd frontend
bun --eval "import { filterKnowledgeReviews, buildReviewDiffSummary, canBatchApprove, canBatchReject, batchSkipReason } from './src/renderer/features/admin/knowledge/reviews/knowledgeReviewView.ts'; ..."
```

结果：通过。
- 搜索 `chat` 返回当前样例页匹配项。
- 未修改草稿返回 `changed=false`。
- 修改 proposed content 返回 `changed=true`。
- 已编辑草稿、citation-fixer、非 pending 均不可批量通过。

本轮未改后端接口，因此不新增 pytest。

## 下一步评估

当前 G6.0 已达到前端审核工作台 MVP 的代码级闭环。下一步按真实使用数据选择：

- 如果真实 pending review 数量较多，进入 G6.1：补后端 batch endpoint、批量审计与更清晰的半失败事务结果。
- 如果真实 review 数量不多，进入 G7：状态仪表板 MVP，优先展示 GBrain 服务、jobs、quality、citation-fixer 维护状态。
