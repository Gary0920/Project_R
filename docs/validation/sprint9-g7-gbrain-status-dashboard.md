# Sprint 9.2 / G7.0 GBrain 状态仪表板验证记录

日期：2026-06-17

## 范围

G7.0 是状态仪表板 MVP，不等于完整 GBrain 管理后台重构。

本轮目标是让管理员一眼判断：
- 是否正常；
- 哪里异常；
- 是否需要处理；
- 应该进入哪个已有维护操作。

本轮只复用现有接口：
- `GET /admin/knowledge/status`
- `GET /admin/knowledge/gbrain/maintenance`
- 复用 G5 quality report view model

本轮未补后端聚合接口，未修改 GBrain 原生代码。

## 实现落点

- `frontend/src/renderer/features/admin/knowledge/status/gbrainStatusTypes.ts`
- `frontend/src/renderer/features/admin/knowledge/status/gbrainStatusView.ts`
- `frontend/src/renderer/features/admin/knowledge/status/GBrainStatusDashboard.tsx`
- `frontend/src/renderer/features/admin/knowledge/status/GBrainHealthSummary.tsx`
- `frontend/src/renderer/features/admin/knowledge/status/GBrainSignalCards.tsx`
- `frontend/src/renderer/features/admin/knowledge/status/GBrainWarningList.tsx`

`AdminSettingsPanel.tsx` 只做挂载和 props 转发，不承载 G7 状态推导。

## 状态推导规则

整体状态优先级固定为：

```text
critical > attention > ok > unknown
```

`unknown` 只在 `knowledgeStatus` 和 `gbrainMaintenance` 关键状态源均缺失时作为整体状态。单个辅助字段缺失不会把整体状态降为 unknown。

### Critical

- `gbrainMaintenance.ok === false`
- doctor / jobs / onboard check 等工具响应明确非 `ok`
- worker 存在 `last_error`
- readiness errors 非空

限制：G7.0 MVP 暂将 `maintenance.ok=false` 视为 critical，后续可按 check severity 细分。后端当前语义是 doctor、status snapshot、jobs、contradictions、onboard check 五项必须全部 `status === "ok"`，否则 `ok=false`。

### Attention

- doctor `health_score < 90`
- worker 未运行
- quality latest 存在且 `ok=false`
- citation-fixer 有 tracked jobs
- contradiction probe 标记疑似冲突
- readiness warnings 非空

质量报告失败只判 attention，不直接判 critical。

### OK

关键状态源存在，且没有 critical / attention 信号。

### Unknown

`knowledgeStatus` 和 `gbrainMaintenance` 均为空，或关键状态源完全无法判断。

## 非目标

- Dream Cycle / Graph / Entity Merge 大重构
- citation-fixer 深度工作台
- contradiction 深度分析页
- 历史趋势图
- 后端 dashboard 聚合接口
- GBrain 原生代码修改

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
bun --eval "import { buildGBrainStatusDashboardView } from './src/renderer/features/admin/knowledge/status/gbrainStatusView.ts'; ..."
```

样例覆盖：
- 空数据 -> unknown
- service error / maintenance false -> critical
- worker last_error -> critical
- quality failed -> attention
- 全部正常 -> ok

结果：

```json
{
  "empty": "unknown",
  "serviceError": "critical",
  "workerError": "critical",
  "qualityFailed": "attention",
  "allOk": "ok"
}
```

## 浏览器验证

已使用当前运行中的前端地址验证：

- 地址：`http://127.0.0.1:5174/`
- 登录账号：`sysadmin / Admin123`
- 路径：设置 -> 管理员 -> GBrain 维护

可见结果：

```text
Overall Health
需关注
signals: Doctor=需关注 / Worker=正常 / Jobs=正常 / Quality=未知
Key Signals
Doctor / Worker / Jobs / Quality
Warnings & Actions
Doctor 需关注
Maintenance Entry Points
刷新状态 / 维护检查 / 质量报告 / Citation-fixer
```

当前真实环境下 quality 尚未生成报告，因此 Quality 显示未知；单个 quality 字段缺失没有把整体状态降为 unknown，整体状态按 Doctor 需关注推导为 attention。

本轮未改后端接口，因此不新增 pytest。
