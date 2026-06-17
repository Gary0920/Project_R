# Sprint 9 GBrain 管理侧总验收

日期：2026-06-17

## 结论

Sprint 9 管理侧知识模块已达到 MVP 代码级闭环：

- G5 质量报告 MVP：通过。
- G6.0 前端审核工作台 MVP：通过，不标记完整 G6。
- G7.0 状态仪表板 MVP：通过，不等于完整 GBrain 管理后台重构。

本轮不继续加功能，后端 batch endpoint、完整审核历史、深度 citation-fixer 工作台、完整状态趋势图和 GBrain 管理后台重构均后置。

## 1. 管理员入口

结果：通过。

- 浏览器验证可登录 `sysadmin / Admin123`。
- 可进入 设置 -> 管理员。
- 可进入 概览 / 知识审核 / GBrain 维护。

## 2. G5 质量报告区

结果：通过。

已验证：
- 无报告状态显示“尚未生成质量报告”。
- 单报告状态可显示摘要和失败 case。
- 单报告不显示伪趋势，显示“历史报告数据不足，暂无法形成趋势”。
- 多报告且 query/think pass rate 可计算时显示趋势点。
- JSON 下载入口保留；无报告时禁用。

样例验证结果：

```json
{
  "no": "尚未生成质量报告",
  "oneFailures": 1,
  "oneTrend": "历史报告数据不足，暂无法形成趋势",
  "manyTrend": 2
}
```

边界记录见：
- `docs/validation/sprint9-gbrain-admin-quality-report.md`

## 3. G6 审核工作台

结果：通过，记为 G6.0 前端审核工作台 MVP，不标记完整 G6。

已验证：
- 知识审核入口可进入。
- 当前真实环境无 pending review，浏览器确认空状态和批量按钮禁用。
- 搜索、diff、批量资格规则用 view model 样例验证。
- 单条详情代码路径显示原 content 和 proposed content。
- proposed content 可提交：后端 `ReviewKnowledgeRequest.content` 会写回 `review.content`。
- 单条驳回不提交 proposed content。
- 批量通过只允许 pending、未编辑草稿、非 citation-fixer 状态不明项。
- 批量驳回只允许 pending。
- 批量结果支持成功 / 失败 / 跳过项展示。

样例验证结果：

```json
{
  "search": 2,
  "diff": true,
  "approveBase": true,
  "rejectBase": true,
  "approveEdited": false,
  "editedReason": "已有本地编辑草稿，只能单条审核",
  "approveFixer": false,
  "approveApproved": false
}
```

限制：
- 当前真实 review 数量为 0，未进行真实 pending review 的浏览器点击审批。
- 本轮未写真实 `app.db` 临时 review 数据。
- 后端 batch endpoint 后置。

边界记录见：
- `docs/validation/sprint9-g6-knowledge-review-workbench.md`

## 4. G7 状态仪表板

结果：通过。

已验证：
- Overall Health 可见。
- Key Signals 可见。
- Warnings & Actions 可见。
- Maintenance Entry Points 可见。
- 空数据 -> unknown。
- maintenance / service error -> critical。
- worker last_error -> critical。
- quality failed -> attention。
- 全部正常 -> ok。

样例验证结果：

```json
{
  "empty": "unknown",
  "critical": "critical",
  "workerError": "critical",
  "qualityFailed": "attention",
  "allOk": "ok"
}
```

浏览器验证：
- 设置 -> 管理员 -> GBrain 维护 可见 G7 dashboard。
- 当前真实环境显示 Overall Health 为“需关注”，依据是 Doctor 需关注，Quality 无报告仅作为单项未知，没有把整体降为 unknown。

边界记录见：
- `docs/validation/sprint9-g7-gbrain-status-dashboard.md`

## 5. 大文件控制

结果：通过。

- `AdminSettingsPanel.tsx` 不再承载 G5/G6/G7 主体逻辑。
  - 当前仅挂载 `KnowledgeReviewPanel` 和 `GBrainStatusDashboard`。
  - 本轮相关 diff 显示该文件净减少：`39 insertions / 210 deletions`。
- `SettingsModal.tsx` 没有新增管理侧业务 UI。
  - 仅做最小 handler 签名调整。
  - 本轮相关 diff：`4 insertions / 20 deletions`。
- 新逻辑主要落在：
  - `frontend/src/renderer/features/admin/knowledge/`
  - `frontend/src/renderer/features/admin/knowledge/reviews/`
  - `frontend/src/renderer/features/admin/knowledge/status/`

## 6. 自动验证

已执行：

```powershell
cd frontend
bun run typecheck
```

结果：通过。

已执行三组 `bun --eval` view model 样例：
- G5 quality report。
- G6 knowledge review。
- G7 status dashboard。

结果：均通过。

## 7. Sprint 9 收尾判断

Sprint 9 可视为管理侧 GBrain MVP 代码级闭环：

- 可进入管理员知识管理入口。
- 管理员可查看质量报告摘要和 JSON。
- 管理员可进入审核工作台。
- 管理员可查看 GBrain 总体状态和关键 warning。
- 结构边界已建立，未继续扩大设置大组件。

后续建议：
- 如果真实 pending review 增长明显，再进入 G6.1 后端 batch endpoint。
- 如果继续管理侧产品化，下一轮应做浏览器/真实数据验收补强，而不是立即堆新功能。
