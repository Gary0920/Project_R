---
name: Sprint 2 Chat 核心痛点
overview: 拆分 AppPage.tsx 这个上帝文件：0a（已完成）抽出 Chat 发送/流式/重生成/快捷键（2620→2334）；0b 继续抽通知/更新/面板/附件 shell 职责逼近 1500，达退出条件即停；随后实现 Sprint 2 三项（C6 输入框自动高度、C3 会话导出、C2 草稿收尾），全程不增大上帝文件。
todos:
  - id: split-apppage-0a
    content: 阶段0a（已完成）：Chat 发送/流式/重生成/快捷键抽成 features/chat/ hooks，AppPage 2620→2334，typecheck 与后端流式回归通过
    status: completed
  - id: split-apppage-0b
    content: 阶段0b（已完成）：抽通知/客户端更新/面板布局/附件上传 4 个 shell hooks 到正确 feature 落点，行为等价（迁移各自 useEffect+cleanup），达退出条件即停
    status: completed
  - id: c6-textarea
    content: 阶段1：C6 输入框自动高度 —— ChatComposer textarea 随 scrollHeight 动态调高 + global.css min/max，落点不回流 AppPage
    status: pending
  - id: c3-export
    content: 阶段2：C3 会话导出 —— 后端薄路由 GET /chat/sessions/{id}/export + export_service.py，前端 api + 会话菜单导出按钮，含权限与 pytest
    status: pending
  - id: c2-verify
    content: 阶段3：C2 草稿收尾 —— 校验 save/load/clear 接线并补切换/刷新恢复、发送清空的验证
    status: pending
  - id: run-gates
    content: 每阶段后运行验证闸门：bun run typecheck + pytest backend/tests/test_chat_phase6.py（由用户执行并反馈）
    status: pending
isProject: false
---

# Sprint 2：Chat 核心痛点（架构优先，先拆后做）

## 背景与结论

Sprint 1 流式接缝功能层面实质完成、质量高（provider 无关、薄路由、可取消、token 正确）。架构地基方面已开始收口：[frontend/src/renderer/pages/AppPage.tsx](frontend/src/renderer/pages/AppPage.tsx) 经 Phase 0a 已从 2620 降到 **2334 行**（Chat 发送/流式/重生成/快捷键已抽成 hooks），但仍高于 1500 红线。Sprint 2 的 C6/C3/C2 还会继续改这个文件，因此先继续 Phase 0b 把剩余 shell 职责抽出，再加功能。

**重要纪律**：拆分是手段不是目的。真正目标是"单一职责、可读、可维护"，1500 是参考线不是硬指标。达到退出条件（见 0b）后**立即停止重构转入功能**，不为凑数字去拆紧贴 JSX 的渲染 glue。

验证闸门（`bun run typecheck`、`pytest backend/tests/test_chat_phase6.py`）需在每阶段后运行（Phase 0a 已由用户确认通过）。

## 当前真实进度

- C2 草稿：`useChatDraft.ts` 已完整，`AppPage.tsx` 已导入 `loadDraft/saveDraft/clearDraft` —— 基本完成，仅需校验接线与验收。
- C6 输入框自动高度：[ChatComposer.tsx](frontend/src/renderer/features/chat/components/ChatComposer.tsx) 仍为 `rows={1}`，无 `scrollHeight` 逻辑 —— 未做。
- C3 会话导出：`backend/app/features/chat/` 下无导出服务/端点 —— 未做。

## 阶段 0a（已完成）：抽出 Chat 发送类职责

已把发送编排、流式控制、重新生成、全局/输入快捷键、草稿、send 结果处理抽成 `features/chat/` hooks（`useChatSendOrchestrator`、`useChatStreamControls`、`useChatRegenerate`、`useChatGlobalShortcuts`、`useChatComposerShortcuts`、`useChatDraft`、`useChatSendResults`）。`AppPage.tsx` 2620 → 2334；typecheck 与后端流式回归已确认通过。

## 阶段 0b（已完成）：抽出剩余 shell 职责

目标：把与 Chat 发送低耦合、高内聚的"壳层"职责抽出 `AppPage.tsx`，归位到正确 feature，使其逼近并力争低于 1500，`pages/` 只剩"组装 + 薄 glue"。

落点纪律（不是搬出 AppPage 就行，要归到正确 feature）：

- 通知中心（`loadNotificationList`/`showNotificationToast`/`refreshNotificationCounts`/`markNotificationReadAndRefresh`/`handleMarkAllNotificationsRead`/`handleNotificationAction`/`handleNotificationActionStatus`，约 L514-652 + 相关 state/refs）→ `features/notifications/hooks/useNotificationCenter.ts`（该目录已有 `state.ts`/`api.ts`/`formatters.ts`）。
- 客户端更新（`checkForClientUpdate`/`startClientUpdateDownload`，约 L652-746 + `clientVersion`/`updateDialogOpen`/`downloadedUpdatePath`/`updateError`/`updateCheckStartedRef`）→ 新建 `features/update/hooks/useClientUpdate.ts`（新目录归属："自动更新"独立关注点，仅 AppPage 壳层调用）。
- 面板布局/拖拽/预览联动（`handleSidebarResizeStart`/`handleWorkspacePanelResizeStart`/`handleAuxiliaryPanelResizeStart`/preview open-close + resize useEffect + 各宽度 state/refs）→ `shared/hooks/useResizablePanels.ts` 或 `features/chat/hooks/`；**先复用/合并已存在的** [useWorkspacePreviewWidth.ts](frontend/src/renderer/features/workspace/hooks/useWorkspacePreviewWidth.ts)，不重复造。
- 附件上传编排（`isUploadingAttachments`/`pendingAttachmentPreviewsRef`/选择上传逻辑）→ `features/chat/`（已有 `attachments.ts`）。

行为等价（关键风险）：通知有 toast 定时器、轮询 interval、去重 ref（`notificationInitializedRef`/`notificationToastIdsRef`），更新有一次性守卫 `updateCheckStartedRef`。每个 hook 必须**完整迁移自己的 useEffect 依赖与 cleanup**，否则会出现重复 toast、重复检查更新等回归。每抽一个 hook 跑一次 typecheck + 手工冒烟。

退出条件（达到即停，不再为数字继续拆）：

- 上述 4 块已抽成各自 hook 并归位；且
- `AppPage.tsx` 只剩 JSX 组装 + 薄 glue（理想 ≤ ~1500；落在 ~1400-1600 但结构干净也算达标）。

完成定义：`AppPage.tsx` 净行数继续下降；`bun run typecheck` 通过；手工冒烟（通知 toast/已读、检查更新一次、面板拖拽/预览宽度恢复、附件上传）无回归。

## 阶段 1：C6 输入框自动高度

- 在 [ChatComposer.tsx](frontend/src/renderer/features/chat/components/ChatComposer.tsx) 给 textarea 增加随 `scrollHeight` 动态调高逻辑（输入/粘贴/清空时重算），上限内滚动。
- 配合 [global.css](frontend/src/renderer/shared/styles/global.css) 的 `.composer textarea` min/max-height。
- 落点在 ChatComposer 内，不回流到 AppPage。

完成定义：多行输入自动增高至上限后内部滚动，发送后回落；`bun run typecheck` 通过。

## 阶段 2：C3 会话导出

- 后端新增薄路由 `GET /chat/sessions/{id}/export?format=markdown|json`（[backend/api/chat.py](backend/api/chat.py) 仅做参数校验与权限），组装逻辑放新文件 `backend/app/features/chat/export_service.py`（含全部消息、角色、时间、引用；非本人会话拒绝）。
- 前端 [features/chat/api.ts](frontend/src/renderer/features/chat/api.ts) 加 `exportChatSession`，会话菜单加"导出"按钮（触发下载）。
- 遵守业务规则：导出是用户带走自己的对话数据，不写工作区、不入库。

完成定义：`pytest`（导出内容完整 + 权限边界）通过；`bun run typecheck` 通过；手工下载校验 markdown/json。

## 阶段 3：C2 草稿收尾与验收

- 校验 `AppPage.tsx`（拆分后落到 hook 内）确实做到：输入变化 `saveDraft`、切换/打开会话 `loadDraft` 回填、发送成功 `clearDraft`。
- 补一处轻量验证（组件/手工）：输入未发送 → 切会话/刷新 → 回到原会话草稿恢复，发送后清空。

完成定义：草稿在切换与刷新后稳定恢复且发送后清空。

## 统一完成定义（每阶段都适用）

- 落点正确（功能归到所属 feature：通知→`features/notifications/`、更新→`features/update/`、面板→`shared/hooks/` 或 `features/chat/`，导出→`app/features/chat/`；`pages/` 只组装）。
- 不增大上帝文件：触碰 `AppPage.tsx` 时净行数下降或持平。
- 薄路由：导出逻辑在 feature 层，路由只校验转发。
- 附验证：`bun run typecheck` + 相关 `pytest`，不污染真实 `app.db`。

## 验证闸门（请你运行）

- 前端：`cd frontend && bun run typecheck`
- 后端：`pytest backend/tests/test_chat_phase6.py`（含流式持久化用例）
- 阶段 2 后追加导出相关 `pytest`。

