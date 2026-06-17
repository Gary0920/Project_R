# Sprint 9.0 GBrain 管理侧质量报告验证记录

日期：2026-06-17

## 范围

本轮只做管理侧知识模块结构 + G5 质量报告 MVP，不做 G6/G7，不新增 chart 依赖，不修改 GBrain 原生代码。

前端落点：
- `frontend/src/renderer/features/admin/knowledge/qualityReportView.ts`
- `frontend/src/renderer/features/admin/knowledge/KnowledgeQualityReportPanel.tsx`
- `frontend/src/renderer/features/admin/knowledge/AdminKnowledgeOverview.tsx`

`AdminSettingsPanel.tsx` 未新增 G5 数据整理、接口调用、状态管理或渲染逻辑。

## 已确认真实数据结构

质量报告来自 `knowledgeStatus.quality_reports`，由后端 manifest 返回：

- `latest`：最近一次完整报告。
- `reports`：最近报告列表。
- `trend`：由后端按真实报告摘要计算出的趋势项。

最新报告摘要优先读取：
- `latest.summary.query`
- `latest.summary.think`
- `latest.summary.failed_cases`
- `latest.summary.preflight_failures`

当 `summary.failed_cases` 缺失或为空时，前端才从 `latest.query.cases` 与 `latest.think.cases` 中提取 `ok=false` 的失败项。

## 数据整理样例覆盖

项目当前没有前端单元测试脚本，`package.json` 仅提供 `typecheck` 与 Playwright E2E。因此本轮将以下样例作为 `qualityReportView.ts` 的手工验证口径：

1. 无报告
   - 输入：`quality_reports` 为空或 `latest=null`。
   - 预期：显示“尚未生成质量报告”；失败列表为空状态；趋势显示“历史报告数据不足，暂无法形成趋势”。

2. 单报告
   - 输入：只有一份 `latest/reports`，且 query/think 均可计算通过率。
   - 预期：显示最新摘要和失败列表；趋势仍显示“历史报告数据不足，暂无法形成趋势”。

3. 多报告
   - 输入：至少两份报告都能计算 `query_pass_rate` 与 `think_pass_rate`。
   - 预期：显示真实 query/think 通过率趋势条；不伪造缺失数据。

4. 缺字段
   - 输入：缺少 `summary` 或 `trend`。
   - 预期：摘要回退到 `query/think` suite；趋势只能从可计算报告派生，仍不足时显示空状态。

5. `failed_cases` 优先
   - 输入：`summary.failed_cases` 非空，同时 `cases` 中也有失败项。
   - 预期：失败列表优先显示 `summary.failed_cases`。

6. 从 cases 提取失败项
   - 输入：`summary.failed_cases` 为空，`query.cases` 或 `think.cases` 存在 `ok=false`。
   - 预期：失败列表显示对应 case id、suite 与 reason。

## 手工 UI 验收点

- 管理员知识概览中能看到最新质量报告摘要。
- 失败 case 列表优先展示在趋势之前。
- warning / preflight 摘要单独展示。
- JSON 下载入口保留，且无报告时禁用。
- 至少两份可计算 query/think 通过率报告时才显示趋势。
- 数据不足时显示“历史报告数据不足，暂无法形成趋势”。
- 不新增大型 chart 依赖。

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
bun --eval "import { buildQualityReportView } from './src/renderer/features/admin/knowledge/qualityReportView.ts'; ..."
```

结果：通过。无报告/单报告显示趋势不足，多报告显示 2 个趋势点；`summary.failed_cases` 缺失时可从 `cases` 提取失败项。

本轮未补后端 adapter，故不新增 pytest。
