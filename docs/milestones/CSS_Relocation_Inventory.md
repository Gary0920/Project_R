# CSS Relocation Inventory — global.css

生成日期: 2026-06-16
源文件行数: 13878
源文件路径: `frontend/src/renderer/shared/styles/global.css`

---

## Inventory 格式

```
selector_or_block / 所属模块 / 原始行号范围 / 目标文件 / 备注
```

---

## 1. Base — 变量 / Reset / 基础元素

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `:root` (HSL variables, tokens, font, shell-radius, layers) | 6–56 | `base.css` | 所有 CSS 变量定义 |
| `:root[data-theme="dark"]` (dark theme tokens) | 58–82 | `base.css` | 暗色主题变量覆盖 |
| `* { box-sizing }` | 84 | `base.css` | 全局重置 |
| `html, body, #root { height: 100% }` | 86 | `base.css` | 全高布局基准 |
| `body` (margin, min-width, color, background) | 88–95 | `base.css` | 基础 body 样式 |
| `:root[data-theme="dark"] body` (dark body bg) | 97–100 | `base.css` | 暗色 body 背景 |
| `button, input, textarea { font/color }` + `a` | 102–103 | `base.css` | 基础表单/链接继承 |
| `button` (默认按钮样式) | 105–121 | `base.css` | 基础按钮设计 |
| `button:hover` | 123–125 | `base.css` | 按钮悬停 |
| `button:active:not(:disabled)` | 127–129 | `base.css` | 按钮按下 |
| `button/input/textarea/select:focus-visible` | 131–137 | `base.css` | 焦点环 |
| `button:disabled` | 139–142 | `base.css` | 按钮禁用态 |
| `.ghost-button` / `.ghost-button:hover` | 144–153 | `base.css` | 幽灵按钮 |
| `.titlebar-no-drag, button, input, textarea, a` | 155–161 | `base.css` | no-drag 规则 |

## 2. Shell — Workbench 壳层布局

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.shell` (flex viewport 布局) | 163–173 | `shell.css` | 主壳层 flex 容器 |
| `.shell-auth` | 175–180 | `shell.css` | 认证页壳层 |
| `.shell-page` | 182–186 | `shell.css` | 页面壳层 |
| `.shell-window-fallback` | 188–195 | `shell.css` | 回退窗口样式 |
| `.fallback-window-strip` | 197–206 | `shell.css` | 回退窗口顶栏 |
| `.fallback-window-title` | 208–214 | `shell.css` | 回退窗口标题 |

## 3. Left Sidebar — 侧边栏

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.chat-sidebar` (弹性容器) | 219–233 | `shell.css` | 左侧边栏卡片容器 |
| `.chat-sidebar.is-resizing` | 235–237 | `shell.css` | 拖拽中禁用选中 |
| `.sidebar-resize-handle` | 239–251 | `shell.css` | 拖拽手柄 |
| `.sidebar-resize-handle:hover/:focus-visible` | 253–257 | `shell.css` | 手柄悬停（实际隐藏） |
| `.sidebar-top` | 259–263 | `shell.css` | 侧栏顶部区域 |
| `.sidebar-brand` | 266–272 | `shell.css` | 品牌标识 |
| `.sidebar-brand-mark` | 274–284 | `shell.css` | 品牌图标 |
| `.sidebar-brand-name` | 286–290 | `shell.css` | 品牌名称 |
| `.mode-switch` (模式切换) | 293–301 | `shell.css` | 滑动指示器容器 |
| `.workspace-selector-area, .sidebar-command-row` | 303–307 | `shell.css` | 分隔线 |
| `.mode-switch-indicator` | 309–320 | `shell.css` | 滑动指示器 |
| `.mode-switch[data-active="agent"] .mode-switch-indicator` | 322–324 | `shell.css` | Agent 模式位置 |
| `.mode-tab` | 326–342 | `shell.css` | 模式标签页 |
| `.mode-tab.is-active` | 343 | `shell.css` | 活跃标签 |
| `.mode-tab:disabled` | 345–348 | `shell.css` | 禁用态 |
| `.new-chat-button` | 350–365 | `shell.css` | 新建会话按钮 |
| `.new-chat-button:hover` | 367–371 | `shell.css` | 新建按钮悬停 |
| `.session-list` / scrollbar | 374–385 | `shell.css` | 会话列表容器 |
| `.session-group-label` | 387–395 | `shell.css` | 会话分组标签 |
| `.sidebar-note` | 397–403 | `shell.css` | 侧栏提示 |
| `.session-item` | 405–420 | `shell.css` | 会话条目 |
| `.session-item:hover` | 422–424 | `shell.css` | 条目悬停 |
| `.session-item.is-active` | 426–428 | `shell.css` | 条目激活态 |
| `.session-item.is-in-left-pane::before` 等 | 430–444 | `shell.css` | 分区指示器 |
| `.session-title` | 446–456 | `shell.css` | 会话标题 |
| `.session-pin-badge` | 464–477 | `shell.css` | 置顶徽章 |
| `.session-time` | 483–487 | `shell.css` | 时间戳 |
| `.session-delete` | 489–506 | `shell.css` | 删除按钮 |
| `.session-item:hover .session-delete` | 508–511 | `shell.css` | 显示删除 |
| `.session-delete:hover` | 513–516 | `shell.css` | 删除悬停 |
| `.sidebar-user` | 519–525 | `shell.css` | 底部用户芯片 |
| `.sidebar-user-avatar` | 527–536 | `shell.css` | 头像容器 |
| `.sidebar-user-avatar.is-text` | 538–543 | `shell.css` | 文字头像 |
| `.sidebar-user-info` | 545–550 | `shell.css` | 用户信息 |
| `.sidebar-user-name` | 552–559 | `shell.css` | 用户名 |
| `.sidebar-user-role` | 561–564 | `shell.css` | 用户角色 |
| `.sidebar-user-actions` | 566–570 | `shell.css` | 用户操作区 |
| `.notification-button` | 572–578 | `shell.css` | 通知按钮 |
| `.icon-button` | 580–597 | `shell.css` | 图标按钮基础 |
| `.workbench-topbar` | 599–610 | `shell.css` | 顶部工具栏 |
| `.workbench-context` | 612–630 | `shell.css` | 上下文区域 |
| `.workbench-business-nav` / `.workbench-system-tools` | 636–651 | `shell.css` | 导航/工具 |
| `.business-tool-button` / hover | 653–677 | `shell.css` | 业务工具按钮 |

## 4. Chat Main — 对话主区域

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.chat-main` | 682–694 | `chat/styles.css` | 主对话卡片 |
| `.chat-workbench` | 696–702 | `chat/styles.css` | 工作区弹性容器 |
| `.chat-conversation-pane` | 704–716 | `chat/styles.css` | 对话面板 |
| `.chat-conversation-pane + .chat-conversation-pane` | 714–716 | `chat/styles.css` | 分割面板分隔 |
| `.chat-conversation-pane.is-active` | 718–720 | `chat/styles.css` | 激活面板 |
| `.chat-conversation-pane.is-attachment-drag-over` | 722–724 | `chat/styles.css` | 拖拽高亮 |
| `.attachment-drop-overlay` | 726–740 | `chat/styles.css` | 附件拖拽覆盖层 |
| `.attachment-drop-overlay > div` | 742–748 | `chat/styles.css` | 覆盖层内容 |
| `.attachment-drop-overlay svg/.iconoir-mask` | 750–755 | `chat/styles.css` | 覆盖层图标 |
| `.attachment-drop-overlay strong/span` | 757–765 | `chat/styles.css` | 覆盖层文字 |
| `.chat-workbench.is-split .chat-conversation-pane` | 767–769 | `chat/styles.css` | 分割模式 |
| `.chat-workbench.is-split .chat-conversation-pane.is-active` | 771–773 | `chat/styles.css` | 分割激活高亮 |
| `.chat-workbench.has-files-pane .chat-conversation-pane` | 775–777 | `chat/styles.css` | 文件面板模式 |
| `.utility-side-pane` | 779–789 | `chat/styles.css` | 工具侧面板 |
| `.utility-side-pane.is-resizing` | 791–793 | `chat/styles.css` | 拖拽禁用 |
| `.utility-resize-handle` / ::after | 795–823 | `chat/styles.css` | 工具面板拖拽手柄 |
| `.utility-side-header` | 825–834 | `chat/styles.css` | 工具面板头部 |
| `.utility-side-header h2/p` | 836–846 | `chat/styles.css` | 头部文字 |
| `.utility-side-body` | 848–852 | `chat/styles.css` | 工具面板内容 |
| `.workspace-files-side-pane .agent-file-panel` | 854–858 | `chat/styles.css` | 文件面板嵌入 |
| `.workspace-files-side-pane:has(.workspace-file-panel-layout.has-preview)` | 860–863 | `chat/styles.css` | 文件预览宽度 |
| `.workspace-file-panel-layout` / `.has-preview` / `.is-crm-standalone` | 865–881 | `chat/styles.css` | 文件面板布局 |
| `.prompt-panel.is-embedded` | 883–895 | `chat/styles.css` | 嵌入提示面板 |
| `.prompt-utility-side-pane` | 897–899 | `chat/styles.css` | 提示工具面板 |
| `.skill-side-row` / hover | 901–921 | `chat/styles.css` | 技能列表行 |
| `.skill-side-icon` | 923–932 | `chat/styles.css` | 技能图标 |
| `.skill-side-copy` | 934–956 | `chat/styles.css` | 技能文字 |
| `.source-preview-body` | 958–962 | `chat/styles.css` | 源码预览体 |
| `.source-preview-index` | 964–974 | `chat/styles.css` | 预览索引标签 |
| `.source-preview-body h3` | 976–979 | `chat/styles.css` | 预览标题 |
| `.source-preview-path/.source-preview-file` | 981–987 | `chat/styles.css` | 预览路径 |
| `.source-preview-markdown` | 989–998 | `chat/styles.css` | 预览 Markdown |
| `.source-preview-markdown > *:first/last-child` | 1000–1006 | `chat/styles.css` | 预览首尾 |
| `:root[data-theme="dark"] .source-preview-index/markdown` | 1008–1017 | `chat/styles.css` | 暗色预览 |
| `.chat-workbench.is-split .message-row` | 1019–1021 | `chat/styles.css` | 分割消息宽度 |
| `.chat-header` | 1023–1031 | `chat/styles.css` | 对话头部 |
| `.chat-header-title` | 1033–1049 | `chat/styles.css` | 头部标题 |
| `.chat-header-actions` | 1051–1055 | `chat/styles.css` | 头部操作按钮 |

## 5. Messages — 消息区域

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.session-search-bar` / `.session-search-input` / `.session-search-count` / `.session-search-close` | 1060–1100 | `chat/styles.css` | 会话搜索栏 |
| `.message-scroll-wrap` / `.message-scroll` / scrollbar | 1102–1119 | `chat/styles.css` | 消息滚动区 |
| `.empty-chat` | 1121–1132 | `chat/styles.css` | 空对话状态 |
| `.empty-chat-mark` | 1134–1145 | `chat/styles.css` | 空状态图标 |
| `.empty-chat h2` / `p` | 1147–1159 | `chat/styles.css` | 空状态文字 |
| `.empty-chat-compact` | 1161–1167 | `chat/styles.css` | 紧凑空状态 |
| `.chat-error` | 1169–1178 | `chat/styles.css` | 错误提示 |
| `.chat-notice` | 1180–1189 | `chat/styles.css` | 通知提示 |
| `.message-row` | 1191–1199 | `chat/styles.css` | 消息行 |
| `.message-body` | 1201–1205 | `chat/styles.css` | 消息体 |
| `.message-meta` | 1207–1214 | `chat/styles.css` | 消息元信息 |
| `.message-meta-spacer` | 1216 | `chat/styles.css` | 弹性分隔 |
| `.message-meta-copy` / `.message-name-line` | 1218–1241 | `chat/styles.css` | 元信息布局 |
| `.message-role-label` / `.message-time` | 1233–1248 | `chat/styles.css` | 角色/时间 |
| `.message-row-loading .message-meta` | 1250–1252 | `chat/styles.css` | 加载态元信息 |
| `.message-row-loading .message-role-label` | 1254–1257 | `chat/styles.css` | 加载态角色 |
| `.message-avatar` | 1259–1270 | `chat/styles.css` | 消息头像 |
| `.message-avatar.is-text` | 1272–1275 | `chat/styles.css` | 文字头像 |
| `.message-bubble` | 1277–1283 | `chat/styles.css` | 消息气泡 |
| `.message-paragraph` | 1285–1291 | `chat/styles.css` | 段落 |
| `.message-heading` | 1293–1307 | `chat/styles.css` | 消息标题 |
| `.message-divider` | 1309–1314 | `chat/styles.css` | 分割线 |
| `.message-list` / li | 1316–1324 | `chat/styles.css` | 列表 |
| `.message-quote` | 1326–1340 | `chat/styles.css` | 引用 |
| `.message-inline-code` | 1342–1350 | `chat/styles.css` | 行内代码 |
| `:root[data-theme="dark"] .message-inline-code` | 1352–1357 | `chat/styles.css` | 暗色行内代码 |
| `.message-source-ref` / hover | 1359–1380 | `chat/styles.css` | 来源引用 |
| `.message-wikilink` | 1382–1385 | `chat/styles.css` | Wiki 链接 |
| `.message-table-wrap` / `.message-table` | 1387–1416 | `chat/styles.css` | 表格 |
| `.message-row-assistant .message-bubble` | 1418–1422 | `chat/styles.css` | AI 消息气泡 |
| `.message-row-user .message-bubble` | 1424–1429 | `chat/styles.css` | 用户消息气泡 |
| `.message-row-failed .message-bubble` | 1431–1434 | `chat/styles.css` | 失败消息 |
| `.message-sources` / item / index | 1436–1495 | `chat/styles.css` | 来源列表 |
| `.message-attachments` / 图片 / 文件 | 1497–1638 | `chat/styles.css` | 附件 |
| `.attachment-lightbox-backdrop` / lightbox / footer | 1640–1713 | `chat/styles.css` | 图片灯箱 |
| `:root[data-theme="dark"] .message-sources-title` 等 | 1715–1757 | `chat/styles.css` | 暗色附件/来源 |
| `.message-file-card` / download | 1759–1802 | `chat/styles.css` | 文件卡片 |
| `.message-agent-suggestion` | 1804–1852 | `chat/styles.css` | Agent 建议卡片 |
| `.message-context-trace` | 1854–1959 | `chat/styles.css` | 上下文追踪 |
| `.message-agent-run-card` / header / progress / event | 1961–2138 | `chat/styles.css` | Agent 运行卡片 |
| `.workspace-agent-run-toast` | 2140–2163 | `chat/styles.css` | Agent toast 通知 |
| `@keyframes workspace-agent-toast-in/out` | 2169–2189 | `chat/styles.css` | Toast 动画 |
| `.workspace-agent-run-header/latest/history` | 2191–2342 | `chat/styles.css` | Agent 运行详情 |
| `:root[data-theme="dark"]` Agent 相关 | 2344–2431 | `chat/styles.css` | 暗色 Agent 样式 |
| `.message-skill-card` / header / fields / output | 2433–2511 | `chat/styles.css` | 技能执行卡片 |
| `.message-row-failed .message-role-label` | 2513–2515 | `chat/styles.css` | 失败消息角色 |
| `.message-error` | 2517–2521 | `chat/styles.css` | 错误消息 |
| `.message-code-block` / toolbar / copy / code | 2523–2587 | `chat/styles.css` | 代码块 |
| `.typing-caret` | 2589–2598 | `chat/styles.css` | 输入光标动画 |
| `@keyframes blink` | 2599 | `chat/styles.css` | 闪烁动画 |
| `.model-badge` | 2601–2613 | `chat/styles.css` | 模型徽章 |

## 6. Composer — 输入区

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.composer-wrap` | 2618–2621 | `chat/styles.css` | 输入区包裹 |
| `.composer-inactive-hint` | 2623–2633 | `chat/styles.css` | 输入禁用提示 |
| `.composer` | 2635–2647 | `chat/styles.css` | 输入卡片容器 |
| `.hidden-file-input` | 2649–2651 | `chat/styles.css` | 隐藏文件输入 |
| `.composer-attachments` | 2653–2657 | `chat/styles.css` | 附件列表 |
| `.composer-attachment-chip` / thumb / kind / name / meta | 2659–2770 | `chat/styles.css` | 附件芯片 |
| `.composer-attachment-remove` | 2783–2803 | `chat/styles.css` | 附件删除 |
| `.composer-attachment-chip .iconoir-mask` | 2805–2809 | `chat/styles.css` | 附件图标 |
| `.composer-uploading` | 2811–2815 | `chat/styles.css` | 上传中提示 |
| `.composer-attachment-consent` | 2817–2870 | `chat/styles.css` | 附件授权确认 |
| `.composer-context-row` / chips | 2872–2944 | `chat/styles.css` | 上下文芯片行 |
| `.composer:focus-within` | 2946–2949 | `chat/styles.css` | 聚焦边框 |
| `.composer textarea` / placeholder | 2951–2969 | `chat/styles.css` | 输入框 |
| `.composer-token-hint` | 2971–2979 | `chat/styles.css` | Token 提示 |
| `.composer-toolbar` | 2981–2990 | `chat/styles.css` | 工具栏 |
| `.composer-hint` | 2992–2995 | `chat/styles.css` | 输入提示 |
| `.composer-send` | 2997–3034 | `chat/styles.css` | 发送按钮 |

## 7. Gate Pages — Onboarding + Login（第一段）

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| **（空注释 — Gate Pages + Settings 合在一起）** | 3036–3042 | — | 仅注释头 |
| `.page` / `.panel` | 3043–3058 | `auth/styles.css` | 通用页面/面板 |
| `.settings-overlay` / `.settings-dialog` 系列 | 3061–3200+ | `auth/styles.css` | Settings 对话框 — 见第10项 |

## 8. Sidebar Collapse — Discord 图标模式

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| *仅注释* | 3505–3507 | — | 仅注释，无实际样式 |

## 9. Context Menu — 右键菜单

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.context-menu-overlay` | 3513–3517 | `shell.css` | 右键菜单覆盖层 |
| `.context-menu` | 3519–3528 | `shell.css` | 右键菜单 |
| `.context-menu-item` | 3530–3548 | `shell.css` | 菜单项 |
| `.context-menu-item.is-disabled` | 3550–3554 | `shell.css` | 禁用项 |
| `.context-menu-item.is-destructive` | 3556–3558 | `shell.css` | 危险项 |
| `.context-menu-item-main` | 3560–3565 | `shell.css` | 菜单项主体 |
| `.context-menu-icon` | 3567–3573 | `shell.css` | 菜单图标 |
| `.context-menu-check/.context-menu-arrow` | 3575–3580 | `shell.css` | 勾选/箭头 |
| `.context-submenu` | 3582–3594 | `shell.css` | 子菜单 |
| `.context-menu-item.has-submenu:hover > .context-submenu` | 3596–3598 | `shell.css` | 子菜单显示 |
| `.context-menu-separator` | 3600–3604 | `shell.css` | 菜单分割线 |

## 10. Search Dialog — 搜索对话框

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.search-dialog-backdrop` | 3610–3619 | `dialogs.css` | 搜索遮罩 |
| `.search-dialog` | 3621–3629 | `dialogs.css` | 搜索框 |
| `.search-dialog-input` / placeholder | 3631–3645 | `dialogs.css` | 搜索输入框 |
| `.search-dialog-results` | 3647–3651 | `dialogs.css` | 搜索结果 |
| `.search-dialog-empty` | 3653–3658 | `dialogs.css` | 空结果 |
| `.search-result-item` / title / preview / workspace | 3660–3691 | `dialogs.css` | 结果项 |

## 11. Tab Bar

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.tab-bar` | 3697–3707 | `shell.css` | 标签栏 |
| `.tab-strip` | 3709–3721 | `shell.css` | 标签条 |
| `.tab-note-btn` | 3723–3743 | `shell.css` | 笔记按钮 |
| `.tab-item` | 3745–3761 | `shell.css` | 标签项 |
| `.tab-item.is-active` | 3763–3770 | `shell.css` | 激活标签 |
| `.tab-item:hover` | 3772–3778 | `shell.css` | 标签悬停 |
| `.tab-item-title` | 3780–3784 | `shell.css` | 标签标题 |
| `.tab-item-close` | 3786–3811 | `shell.css` | 标签关闭 |
| `.tab-add-btn` | 3813–3832 | `shell.css` | 新增标签 |
| `.tab-drag-spacer` | 3834–3838 | `shell.css` | 拖拽空间 |
| `.window-controls` / `.window-control-btn` / `.window-control-close` | 3840–3873 | `shell.css` | 窗口控制按钮 |
| `.workbench-system-tools .window-controls/btn/close` | 3875–3892 | `shell.css` | 系统工具中的窗口控制 |

## 12. Quick Notes (Scratch Pad)

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.scratch-pad-workspace` | 3903–3909 | `workspace/styles.css` | 速记笔记工作区 |
| `.scratch-pad` | 3911–3918 | `workspace/styles.css` | 速记容器 |
| `.scratch-pad-project` | 3920–3929 | `workspace/styles.css` | 项目标题栏 |
| `.scratch-pad-project > div` | 3931–3936 | `workspace/styles.css` | 项目信息 |
| `.scratch-pad-project strong/span` | 3938–3946 | `workspace/styles.css` | 项目文字 |
| `.scratch-pad-close` | 3948–3964 | `workspace/styles.css` | 关闭按钮 |
| `.scratch-pad-live-panel` | 3966–3971 | `workspace/styles.css` | 实时编辑面板 |
| `.markdown-live-editor` / .cm-editor / 各 CodeMirror 类 | 3973–4139 | `workspace/styles.css` | Markdown 编辑器样式 |
| `.scratch-pad-toolbar` | 4141–4150 | `workspace/styles.css` | 工具栏 |
| `.scratch-pad-export-btn` | 4152–4168 | `workspace/styles.css` | 导出按钮 |
| `.scratch-pad-hint` | 4170–4174 | `workspace/styles.css` | 提示文字 |

## 13. Message Actions

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.message-actions` / user / show/hide | 4180–4197 | `chat/styles.css` | 消息操作栏 |
| `.message-action-btn` / hover / disabled / states | 4199–4270 | `chat/styles.css` | 操作按钮 |
| `.message-action-check` / `.message-action-star` | 4272–4287 | `chat/styles.css` | 勾选/星标 |
| `:root[data-theme="dark"] .message-action-btn.is-copied` | 4289–4292 | `chat/styles.css` | 暗色复制态 |
| `.message-version-bar` | 4294–4306 | `chat/styles.css` | 版本栏 |
| `.message-row-user .message-version-bar` | 4308–4310 | `chat/styles.css` | 用户版对齐 |
| `.message-version-btn` | 4312–4333 | `chat/styles.css` | 版本按钮 |
| `.message-edit-box` / textarea / actions | 4335–4375 | `chat/styles.css` | 编辑框 |

## 14. Chat Header Buttons

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.chat-header-actions`（重复定义） | 4449–4453 | `chat/styles.css` | 头部按钮 |
| `.prompt-menu` / `.prompt-menu-item` | 4455–4478 | `chat/styles.css` | 提示菜单 |

## 15. Composer Enhancements

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.composer-attachments`（重复定义） | 4484–4489 | `chat/styles.css` | 附件列表（增强） |
| `.attachment-pill` / name / remove | 4491–4517 | `chat/styles.css` | 附件药丸 |
| `.composer-temp-slider` / `.composer-temp-input` | 4519–4531 | `chat/styles.css` | 温度滑块 |
| `.composer-mode-toggles` / `.composer-mode-toggle` | 4533–4573 | `chat/styles.css` | 模式切换按钮 |

## 16. Notification Badge / Popover / CRM / Undo Toast

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.notification-badge` | 4579–4594 | `shell.css` | 通知徽章 |
| `.notification-popover` / header / mark-read | 4596–4643 | `shell.css` | 通知弹出面板 |
| `.notification-summary` | 4645–4673 | `shell.css` | 通知摘要 |
| `.notification-tabs` / tab | 4675–4711 | `shell.css` | 通知标签页 |
| `.notification-list` / scrollbar | 4713–4734 | `shell.css` | 通知列表 |
| `.notification-update-entry` | 4736–4770 | `shell.css` | 更新条目 |
| `.notification-empty` | 4772–4777 | `shell.css` | 空通知 |
| `.notification-item` / main / meta / h3 / p / actions | 4779–4889 | `shell.css` | 通知项 |
| `.notification-action-primary/secondary` | 4891–4908 | `shell.css` | 通知操作按钮 |
| `.notification-toast` / title / body | 4910–4949 | `shell.css` | Toast 通知 |
| `@keyframes toast-in` | 4926–4929 | `shell.css` | Toast 动画 |
| `:root[data-theme="dark"]` 通知相关 | 4951–4991 | `shell.css` | 暗色通知 |
| `.crm-workbench-body` / hero / icon / flow / sections | 4993–5111 | `workspace/styles.css` | CRM 工作台 |
| `.message-undo-toast` / button | 5113–5133 | `chat/styles.css` | 撤销 Toast |

## 17. Workspace Selector + Settings + Admin（大段）

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.workspace-selector` / label / area / create / list | 5139–5225 | `workspace/styles.css` | 工作区选择器 |
| `.session-rename-input` | 5227–5237 | `chat/styles.css` | 会话重命名输入 |
| `.archive-list` | 5240–5244 | `settings/styles.css` | 归档列表 |
| `.settings-admin-panel` / wide / prompt-grid / editor | 5246–5295 | `settings/styles.css` | Settings 面板 |
| `.settings-tutorial` | 5297–5311 | `settings/styles.css` | Settings 教程 |
| `.settings-shortcut-row` | 5313–5327 | `settings/styles.css` | 快捷键设置 |
| `.settings-section-title` / actions | 5329–5345 | `settings/styles.css` | 设置区块标题 |
| `.admin-section` | 5347–5357 | `settings/styles.css` | 管理区块 |
| `.admin-metric-grid` | 5359–5390 | `settings/styles.css` | 指标网格 |
| `.admin-regression-report` / summary | 5392–5407 | `settings/styles.css` | 回归报告 |
| `.status-pill` / success / warning | 5409–5427 | `settings/styles.css` | 状态药丸 |
| `.admin-create-user` | 5429–5457 | `settings/styles.css` | 创建用户表单 |
| `.admin-maintenance-form` | 5459–5559 | `settings/styles.css` | 维护表单 |
| `.admin-gbrain-panel` / actions | 5468–5512 | `settings/styles.css` | GBrain 管理面板 |
| `.admin-list` / `.admin-row` / tall / strong/span | 5560–5608 | `settings/styles.css` | 管理列表 |
| `.admin-maintenance-card` / warning | 5610–5648 | `settings/styles.css` | 维护卡片 |
| `.admin-row-actions` | 5650–5691 | `settings/styles.css` | 行操作 |
| `.admin-audit-filters` | 5663–5685 | `settings/styles.css` | 审计过滤器 |
| `.admin-two-col` / `.admin-token` | 5693–5705 | `settings/styles.css` | 两列/标签 |
| `.admin-sub-tabs` / tab / badge | 5708–5761 | `settings/styles.css` | 管理子标签页 |
| `.admin-toolbar` / search / combo | 5763–5806 | `settings/styles.css` | 管理工具栏 |
| `.admin-table` / header / row / cell / scrollbar | 5809–5917 | `settings/styles.css` | 管理表格 |
| `.admin-users-table-grid` | 5918–5920 | `settings/styles.css` | 用户表格网格 |
| `.admin-table-row.is-disabled-user` | 5922–5929 | `settings/styles.css` | 禁用用户行 |
| `.admin-user-identity` | 5931–5956 | `settings/styles.css` | 用户身份 |
| `.admin-role-select` / tag / is-admin | 5958–6025 | `settings/styles.css` | 角色选择/标签 |
| `.admin-status-badge` | 6027+ | `settings/styles.css` | 状态徽章 |
| （剩余 admin 样式至 ~6801） | 6028–6801 | `settings/styles.css` | 后续 admin 样式 |

## 18. Proma-aligned Refinements + Iconoir + Workspace Refinements

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.iconoir-mask` | 6806–6814 | `base.css` | SVG 图标遮罩 |
| `.mode-switch[data-active="agent"]` / `["chat"]` | 6816–6822 | `shell.css` | 模式滑动修正 |
| `.mode-tab .iconoir-mask` / `.tab-item-icon .iconoir-mask` | 6824–6827 | `shell.css` | 图标尺寸 |
| `.sidebar-command-row` | 6829–6833 | `shell.css` | 命令按钮行 |
| `.sidebar-search-button` | 6835–6853 | `shell.css` | 搜索按钮 |
| `.workspace-selector-area`（覆盖） | 6855–6857 | `workspace/styles.css` | 选择器区域 |
| `.workspace-section-toggle` / quick-create | 6859–6878 | `workspace/styles.css` | 区块开关 |
| `.workspace-section-title` | 6880–6897 | `workspace/styles.css` | 区块标题 |
| `.workspace-chevron` | 6899–6907 | `workspace/styles.css` | 折叠箭头 |
| `.workspace-list` / group / item | 6909–6998 | `workspace/styles.css` | 工作区列表精修 |
| `.workspace-row-actions` | 7000+ | `workspace/styles.css` | 行操作 |
| （剩余至 8486） | 7001–8486 | `workspace/styles.css` | 后续 workspace 样式 |

## 19. Responsive — 800x600 最小窗口适配

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `@media (max-width: 900px)` | 8490–8513 | `shell.css` | 响应式布局适配 |

## 20. Phase 9B — Prompt Panel / Workspace Files / Sidebar Refinements

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.workspace-section-header` | 8519–8529 | `workspace/styles.css` | 区块头部 |
| `.workspace-section-title small` | 8531–8539 | `workspace/styles.css` | 标题小字 |
| `.workspace-create-icon` | 8541–8557 | `workspace/styles.css` | 创建图标按钮 |
| `.sidebar-section-heading` | 8559–8564 | `shell.css` | 侧栏分区标题 |
| `.icon-button.is-active` / `.is-reserved` | 8566–8573 | `shell.css` | 图标按钮活动态 |
| `.prompt-panel-overlay` | 8575–8582 | `workspace/styles.css` | 提示面板遮罩 |
| `.workspace-files-overlay` / drawer | 8584–8628 | `workspace/styles.css` | 文件面板抽屉 |
| `.prompt-panel` / header / body | 8630–8686 | `workspace/styles.css` | 提示面板 |
| `.prompt-section` / title / row / icon / copy / badge | 8688–8850 | `workspace/styles.css` | 提示列表 |
| `:root[data-theme="dark"] prompt 相关` | 8850–8904 | `workspace/styles.css` | 暗色提示面板 |
| `.prompt-empty` / create-block / trigger | 8906–8931 | `workspace/styles.css` | 提示创建 |
| `.prompt-create-name/content/actions` | 8933–8962 | `workspace/styles.css` | 提示编辑表单 |
| `.empty-agent` | 8964–8998 | `workspace/styles.css` | 空 Agent 状态 |
| `.agent-file-panel` | 8999–9015 | `workspace/styles.css` | Agent 文件面板 |
| `.agent-file-panel-header` | 9017–9039 | `workspace/styles.css` | 文件面板头部 |
| `.agent-file-panel-icon` | 9041–9049 | `workspace/styles.css` | 面板图标 |
| `.agent-file-panel-header h2/p` | 9051–9061 | `workspace/styles.css` | 面板标题 |
| `.agent-file-panel-note` / empty / error / success | 9063–9105 | `workspace/styles.css` | 面板提示 |
| `.workspace-confirm-card` | 9107–9167 | `workspace/styles.css` | 确认卡片 |
| `:root[data-theme="dark"] agent-file-panel 相关` | 9169–9265 | `workspace/styles.css` | 暗色文件面板 |
| `.workspace-confirm-actions button:disabled` | 9267–9270 | `workspace/styles.css` | 禁用确认按钮 |
| `.agent-file-empty` | 9272–9281 | `workspace/styles.css` | 空文件面板 |
| `.workspace-file-breadcrumb` 及后续 | 9283+ | `workspace/styles.css` | 文件面包屑 |
| （剩余至 11882） | 9283–11882 | `workspace/styles.css` | 其余 workspace 文件样式 |

## 21. V3.0-A Additions — Confirm Dialog / Skill Panel / Update Dialog

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.modal-overlay` / `.modal-card` / `.modal-close` | 11887–11929 | `dialogs.css` | 通用模态框 |
| `.settings-modal-card` / `.admin-panel-card` | 11931–11937 | `dialogs.css` | 设置/管理模态框 |
| `.confirm-overlay` | 11939–11947 | `dialogs.css` | 确认弹窗覆盖层 |
| `.update-dialog-backdrop` / `.update-dialog` | 11949–11970 | `dialogs.css` | 更新对话框 |
| `.update-dialog-header` / h2 / p | 11972–11990 | `dialogs.css` | 更新头部 |
| `.update-dry-run` | 11992–12003 | `dialogs.css` | 更新测试标签 |
| `.update-version-meta` | 12005–12022 | `dialogs.css` | 版本信息 |
| `.update-release-notes` | 12024–12042 | `dialogs.css` | 更新日志 |
| `.update-download-panel` | 12044–12046 | `dialogs.css` | 下载面板 |
| `.update-progress-track` / meta | 12048–12070 | `dialogs.css` | 下载进度 |
| `.update-failure-message` | 12072–12080 | `dialogs.css` | 更新失败 |
| `.update-dialog-actions` | 12082+ | `dialogs.css` | 更新操作按钮 |
| （后续至 ~12404） | 12082–12404 | `dialogs.css` | 其余 dialog 样式 |

## 22. Gate Pages 副本 — flat immersive layout

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.gate-page` | 12409–12417 | `auth/styles.css` | Gate 页面容器 |
| `.gate-ambient` | 12419–12424 | `auth/styles.css` | 环境背景 |
| `.aurora-blob` / .blob-1/2/3 动画 | 12426–12458 | `auth/styles.css` | 极光动画 |
| `@keyframes drift-1/2/3` | 12460–12476 | `auth/styles.css` | 漂移动画 |
| `.gate-content` | 12478–12486 | `auth/styles.css` | 内容容器 |
| `@keyframes gate-enter` | 12488–12491 | `auth/styles.css` | 入场动画 |
| `.gate-brand` / `.gate-mark` / `.gate-title` / `.gate-lead` | 12493–12527 | `auth/styles.css` | 品牌区域 |
| `.gate-divider` | 12529–12534 | `auth/styles.css` | 分割线 |
| `.gate-status` / pulse / text / dot | 12537–12604 | `auth/styles.css` | 状态指示 |
| `@keyframes pulse` / `@keyframes status-pop` | 12606–12646 | `auth/styles.css` | 状态动画 |
| `.gate-footer` / `.gate-login-btn` 等（至 ~12846） | 12648–12846 | `auth/styles.css` | Gate 底部/登录按钮 |

## 23. Animated Login Page

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.alp-page` | 12848–12854 | `auth/styles.css` | 动画登录页容器 |
| `.alp-left` / ::before / ::after | 12856–12889 | `auth/styles.css` | 左侧插图区 |
| `.alp-logo` | 12891–12911 | `auth/styles.css` | Logo |
| `.alp-characters-wrapper` / scene | 12913–12927 | `auth/styles.css` | 角色容器 |
| `.alp-character` / `.alp-char-purple/black/orange/yellow` | 12929–12969 | `auth/styles.css` | 角色块 |
| `.alp-eyes` / 各角色眼睛 | 12971–13017 | `auth/styles.css` | 眼睛动画 |
| `.alp-yellow-mouth` / `.alp-orange-mouth` | 13019–13041 | `auth/styles.css` | 嘴巴动画 |
| `@keyframes alp-shake-head` 及更多 alp 动画 | 13043+ | `auth/styles.css` | 摇头动画 |
| （剩余至 ~13318） | 13043–13318 | `auth/styles.css` | 其余登录页样式 |

## 24. Loading Placeholder

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| `.message-row-loading` | 13323–13325 | `chat/styles.css` | 加载态消息行 |
| `.loading-placeholder-inner` / inline / text | 13327–13345 | `chat/styles.css` | 加载占位符 |
| `.pl` / `.pl__ring` / a/b/c/d | 13347–13373 | `chat/styles.css` | 环形加载动画 |
| `@keyframes ringA/B/C/D` | 13375–13618 | `chat/styles.css` | 环转动画 |

## 25. Workbench Refresh — 第一阶段覆盖

| 块 | 行号范围 | 目标文件 | 备注 |
|---|---|---|---|
| 字体大小覆盖（`.mode-tab`、`.session-item` 等） | 13623–13643 | `shell.css` | 字号调整 |
| `.sidebar-note` 调整 | 13640–13643 | `shell.css` | 笔记字号 |
| `.empty-chat` 精简 | 13645–13667 | `chat/styles.css` | 空状态精简 |
| `.icon-button.is-active` / `[aria-expanded]` | 13669–13675 | `shell.css` | 活动态按钮 |
| `focus-visible` 集中定义 | 13677–13684 | `base.css` | 焦点样式 |
| `.chat-header-actions` 间距 | 13686–13688 | `chat/styles.css` | 头部间距 |
| `.chat-header-tool` | 13690–13693 | `chat/styles.css` | 头部工具 |
| `.message-sources.is-compact` | 13695–13719 | `chat/styles.css` | 紧凑来源 |
| `.loading-placeholder-inner` 覆盖 | 13721–13728 | `chat/styles.css` | 加载布局 |
| `.loading-process-text` | 13730–13742 | `chat/styles.css` | 加载过程文字 |
| `.message-agent-plan-grid` | 13744–13772 | `chat/styles.css` | Agent 计划网格 |
| `.message-agent-plan-actions` | 13774–13791 | `chat/styles.css` | 计划操作 |
| `:root[data-theme="dark"] Workbench 覆盖` | 13793–13831 | `shell.css` | 暗色覆盖 |
| `@media (max-width: 900px)` 响应式 | 13833–13867 | `shell.css` | 响应式覆盖 |
| `@media (prefers-reduced-motion)` | 13869–13878 | `base.css` | 减少动效 |
