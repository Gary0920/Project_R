# 前端 CSS Relocation 安全拆分计划

## Summary

本任务不是 CSS 重构，只是 CSS relocation：把 [global.css](D:/Gary/System-Building/02-Ongoing/Project_R/frontend/src/renderer/shared/styles/global.css) 中的大块样式按明确区间搬运到目标文件，降低单文件体量。不得修改视觉、不得清理重复、不得合并规则、不得自由优化选择器。

## Mandatory Rules

- 只允许移动 CSS 代码块，不允许改写 CSS 内容。
- 不得修改 selector。
- 不得修改 property、value、单位、变量名。
- 不得合并重复样式。
- 不得删除注释。
- 不得格式化全文件。
- 不得改 class 命名。
- 不得拆散同一个连续 CSS 区间内的规则。
- 必须保留 `git diff` 中已有未提交改动。
- 必须保留原始 CSS 执行顺序；拆分后的 `@import` 顺序必须按原 `global.css` 中各模块首次出现顺序决定。
- 遇到不确定归属的块，留在 `global.css`，不要猜。
- 每次只搬一类样式，提交给 Codex 审查后再继续下一类。

## Step 1: CSS Inventory First

其他 Agent 第一轮只允许生成 Inventory，不得改文件。

Inventory 格式必须包含：

```text
selector_or_block / 所属模块 / 原始行号范围 / 目标文件 / 备注
```

必须覆盖：

- `:root`、reset、body、全局 button/input/focus/token
- Shell / Workbench 壳层
- Dialog / Modal / Confirm / Update 弹窗
- Auth / Login / Onboarding
- Chat / Messages / Composer / Session / Loading
- Workspace / Files / Members / Meeting / CRM / GBrain
- Settings / Admin
- 不确定归属块

Inventory 完成后，由 Codex 审查区间和目标文件，再允许进入搬运。

## Step 2: Target Files

默认目标文件：

```css
@import "./base.css";
@import "./shell.css";
@import "./dialogs.css";

@import "../../features/auth/styles.css";
@import "../../features/chat/styles.css";
@import "../../features/workspace/styles.css";
@import "../../features/settings/styles.css";
```

但最终 `@import` 顺序必须以 Inventory 里确认的原始出现顺序为准。如果原 `global.css` 中 auth 样式先于 chat 样式出现，就按原顺序导入，不按“看起来更整齐”的功能顺序强排。

## Step 3: Relocation Batches

按低风险区间分批搬运：

1. `base.css`：只搬 `:root`、dark theme token、reset、body、基础交互控件。
2. `shell.css`：只搬 Shell、Sidebar、Workbench topbar 等壳层区间。
3. `dialogs.css`：只搬 modal、confirm、update dialog、通用 overlay 区间。
4. `auth/styles.css`：只搬 Onboarding、Login、Animated Login Page 区间。
5. `chat/styles.css`：只搬 Chat、Messages、Composer、Session search、Loading、Jump bar 区间。
6. `workspace/styles.css`：只搬 Workspace、Files、Members、Meeting、CRM、GBrain 相关区间。
7. `settings/styles.css`：只搬 Settings、Admin 相关区间。
8. 剩余不确定样式留在 `global.css`，由 Codex 单独审查。

每个 batch 后必须检查：

- 原区间已完整移动。
- 注释一起移动。
- 前后相邻块没有被误删。
- `git diff` 中已有新增样式仍存在。
- 未出现 selector/property 改写。

## Verification

每个 batch 后运行：

```powershell
cd frontend
bun run typecheck
```

全部完成后运行：

```powershell
cd frontend
bun run build
```

Codex 审查重点：

- `global.css` 是否只剩 import 和明确暂留块。
- import 顺序是否保持原始 cascade。
- 是否有未提交新增样式丢失。
- 是否出现非 relocation 修改。
- 是否误拆 media query、keyframes、dark theme override、animation 块。

## Assumptions

- 其他 Agent 只负责机械搬运，不负责判断样式优劣。
- Codex 负责审查 Inventory、diff、顺序和验证结果。
- 本任务不处理组件拆分、不改 JSX、不改设计语言、不做视觉优化。
