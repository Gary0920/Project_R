/goal 完成 Project_R 下一次内测上线前 Chat 与 GBrain 知识库功能的 P0 闭环，并在 P0 全部验证通过后实现员工侧知识库浏览/搜索薄入口。

First action: 先读取并核对以下文件，然后回报状态计数与当前真实代码状态，再继续执行：
  - docs/milestones/Project_R 开发流程V2.2_Claude 评估.md
  - docs/milestones/Project_R 开发流程V2.0.md
  - AGENTS.md
  - Claude.md 或 CLAUDE.md（以仓库真实文件名为准）
  - docs/design/ui-design-language.md
  - frontend/src/renderer/features/workspace/components/WorkspaceFileRow.tsx
  - frontend/src/renderer/features/workspace/components/WorkspaceFilePanelHeader.tsx
  - frontend/src/renderer/features/workspace/styles.css
  - frontend/src/renderer/pages/AppPage.tsx
  - backend/app/features/knowledge/sources.py
  - backend/app/features/knowledge/adapter.py
  - backend/api/rag.py
  - frontend/src/renderer/features/chat/
  - frontend/src/renderer/features/knowledge/
报告：
  1. AppPage.tsx 当前行数；
  2. 文件面板缺失 CSS 类数量；
  3. Chat 会话错误态相关 state/调用点数量；
  4. /query source scope 当前行为；
  5. 是否已存在员工侧独立知识库浏览/搜索端点；
  6. 当前可运行的验证命令清单。

Scope:
  - P0 必做：
    1. 修复项目工作区文件管理面板 UI 回归；
    2. 修复 Chat “无法加载会话列表”误报错误横幅；
    3. 修复项目工作区 /query source scope，使其符合规则：项目工作区查询 company-wiki + 当前项目 source；个人工作台只 company-wiki；客户工作区只客户情报 source；
    4. 确认并补齐 GBrain Think 生产门禁说明：GBRAIN_THINK_ENABLED、GBRAIN_THINK_SOURCE_SCOPE_VERIFIED、OAuth/client 配置；
    5. 补对应测试与最小端到端验证。
  - P1 仅在 P0 全部通过后执行：
    1. 增加面向普通员工的知识库浏览/搜索薄端点；
    2. 增加前端独立知识库浏览/搜索入口或面板；
    3. 搜索必须遵守同一 source scope 边界。
  - 可改范围：
    - frontend/src/renderer/features/workspace/
    - frontend/src/renderer/features/chat/
    - frontend/src/renderer/features/knowledge/
    - frontend/src/renderer/shared/ 中必要的通用 hook/component
    - backend/api/rag.py（只能保持薄路由）
    - backend/app/features/knowledge/
    - backend/tests/
    - frontend/e2e/ 或现有前端测试位置
    - .env.example（只写示例变量，不写真实密钥）
  - 不在本 goal 内做：
    - 不做 Agent 文档生成、Excel/PPT/PDF、邮件草稿、业务 Skill；
    - 不做普通 Chat 自动隐式查 GBrain，除非已有代码路径明确要求修正；
    - 不做 GBrain schema/entity enrichment/graph/timeline/citation 替代实现；
    - 不重构无关页面；
    - 不启动开发服务器，除非用户明确要求。

Constraints:
  - 始终遵守 AGENTS.md / Claude.md 的三阶段规则、真实数据隔离规则、GBrain 边界规则、业务文件容器规则和代码结构与可维护性准则。
  - 使用简体中文汇报。
  - 代码结构优先：不得把新逻辑堆进上帝文件。AppPage.tsx、SettingsModal.tsx、backend/api/chat.py、ChatMessageList.tsx、AppWorkspaceChrome.tsx 触碰时必须净行数下降或持平；pages/ 只做组装。
  - 前端视觉修改必须先看 docs/design/ui-design-language.md，复用既有 token、尺寸、间距、圆角、颜色；不得自创视觉体系。
  - 文件面板修复采用方案 A：保留知识状态徽章功能，补齐样式与网格布局，而不是粗暴回退功能。
  - WorkspaceFileRow 的布局必须能容纳 icon、name、size、rag badge，不允许中文标签被挤成竖排。
  - 必须补齐或修正这些 CSS 类：workspace-rag-badge、workspace-rag-retry、workspace-file-primary-action、workspace-file-action、workspace-file-action-menu、workspace-file-action-menu-wrap、is-compact-actions；确认无引用后再删除孤儿类 workspace-file-upload-btn / workspace-file-actions。
  - Chat 错误态必须按 workspace/session 隔离或在成功加载后清理，不能出现“会话列表已显示但顶部仍提示无法加载会话列表”的矛盾态。
  - /query source scope 必须严格符合：
    - 个人工作台：company-wiki only；
    - 项目工作区：company-wiki + 当前项目 source；
    - 客户工作区：客户情报 source only，不叠加 company-wiki 或项目 source。
  - backend/api/rag.py 只能做参数校验和转发；source scope、GBrain adapter、搜索/浏览业务逻辑必须下沉到 backend/app/features/knowledge/。
  - 不得修改真实 backend/app.db，不得污染 backend/workspace_data/user、project、customer 或正式 GBrain source；测试必须用临时 DB、临时 workspace root、fixture 或 monkeypatch。
  - 不写死 D:/、C:/、localhost；路径使用跨平台 API；前端后端地址继续走既有 server state。
  - 不新增依赖，除非先停止并说明原因、影响和验证方式。
  - 不通过改测试、skip 测试、删除断言来制造通过。
  - 不提交代码、不 push、不创建 PR，除非用户明确要求。

Done when:
  1. 文件面板 UI 回归已修复：
     - WorkspaceFileRow 不再出现“回收站/目录/状态徽章”逐字竖排；
     - WorkspaceFilePanelHeader 标题、面包屑、上传/新建/菜单按钮不互相挤压；
     - 窄宽时按钮文字可隐藏但图标仍可用；
     - 浏览器或截图验证项目工作区文件管理面板布局正常。
  2. 文件面板 CSS 已完成结构化收口：
     - 缺失的新类都有样式；
     - 确认无引用后清理旧孤儿类；
     - 未新增全局污染性选择器；
     - 说明复用了哪些 ui-design-language token。
  3. Chat 会话错误横幅已修复：
     - listChatSessions 成功后清理错误态；
     - 切换 workspace/session 不保留旧错误；
     - 请求失败时不与 stale session list 产生矛盾展示；
     - 手工或测试覆盖“成功加载后无红条、失败时错误状态合理”。
  4. 项目工作区 /query source scope 已修复并有测试：
     - 个人工作台只查 company-wiki；
     - 项目工作区查 company-wiki + 当前项目 source；
     - 客户工作区只查客户 source；
     - 用 backend 测试覆盖三种 workspace scope，测试不触碰真实数据。
  5. GBrain Think 生产门禁已明确：
     - .env.example 补充 GBRAIN_THINK_ENABLED、GBRAIN_THINK_SOURCE_SCOPE_VERIFIED 及必要 OAuth/client 示例说明；
     - 文档或最终总结说明如果门禁未开启，/query 会如何降级。
  6. P0 验证全部通过：
     - cd frontend && bun run typecheck 退出码 0；
     - cd backend && .\venv\Scripts\python.exe -m pytest tests/<相关 knowledge/chat/workspace 测试文件>.py 退出码 0；
     - 若新增或修改 e2e，则对应 e2e 通过；
     - 最终 summary 粘贴命令和结果摘要。
  7. 如果 P0 已全部通过，再实现 P1 员工侧知识库浏览/搜索：
     - 后端提供只读 list/search 薄端点，业务逻辑在 backend/app/features/knowledge/；
     - 前端提供普通员工可见入口，区别于 Chat 的 /query；
     - 搜索结果支持 source/type/time 中至少 source 或 type 过滤；
     - 点击结果可打开既有来源预览或把问题带入 /query；
     - 三类 workspace scope 测试通过。
  8. 架构完成定义满足：
     - 新逻辑落在对应 feature/shared 模块；
     - 路由保持薄；
     - 没有新增死代码、投机空壳、重复 if/else 调用点；
     - 触碰的大文件净行数下降或持平；
     - 最终 summary 列出每个修改文件、所属模块、为什么落点正确、验证命令、验证结果、未验证风险。

Stop if:
  - 需要修改真实 backend/app.db、真实 workspace_data、正式 GBrain source 或真实用户/工作区数据。
  - 修复 /query scope 需要 GBrain adapter 支持多 source 但当前接口无法表达；此时停止并报告 adapter 缺口，不要伪造联合查询。
  - 需要新增依赖或安装依赖。
  - 需要修改 AGENTS.md / Claude.md / PRD / ADR 才能改变产品边界。
  - 需要解冻 intent.py 自动意图识别或把普通 Chat 改成默认查知识库。
  - 现有测试开始失败；这是 regression，不要靠改测试、skip、xfail 或删除断言解决。
  - TypeScript typecheck 出现新增 any/类型绕过，且无法在当前 scope 内合理修复。
  - 文件面板修复需要大规模重写 workspace 文件管理组件；先停止并提出最小修复方案。
  - P0 未验证通过时，不要开始 P1 知识库浏览/搜索。
  - git diff 显示超出 Scope 的无关文件被修改。
  - token 预算不足以完成 P1；必须先完成 P0 并总结，不要半成品推进。
