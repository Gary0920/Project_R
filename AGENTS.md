# AGENTS.md — Project_R Agent 工作规则

Project_R 是公司内部 AI 智能办公辅助系统，也是 Gary 用来实验和掌握 AI Agent 工程技能的长期项目。任何 Agent 接手本项目时，都必须遵守本文件；历史 Claude Code 规则不再作为必需的同步维护对象。

## 文档分工

| 文件 | 职责 |
|---|---|
| `AGENTS.md` | Codex / 通用 Agent 工作规则，本文件 |
| `Project_R PRD.md` | 产品范围、目标用户、长期能力边界 |
| `Project_R 开发流程.md` | 阶段顺序、任务清单、完成标志、实现状态，checklist 的唯一维护处 |
| `Project_R V3.0 修改方案.md`（如存在） | V3.0 Proma shell 重构分阶段方案与已确认设计决策 |
| `Project_R 业务工作流清单.md` | 企业业务 Skill 候选清单与实现状态 |
| `docs/ui-design-language.md` | Project_R 前端视觉语言、选中态、控件尺寸和 UI 修改约束 |
| `docs/agents/skills-design.md` | Project_R 业务 Skill 设计规范 |
| `docs/gbrain-feature-inventory.md` | GBrain 原生功能盘点矩阵 |
| `docs/gbrain-ingest-workflow.md` | Project_R 原始资料进入 GBrain source 的导入、提炼、审核和索引流程 |
| `docs/gbrain-adaptation-progress.md` | Project_R 对 GBrain 的适配进度、未闭环项和下一步顺序 |

当前仓库核心文档以根目录版本为准，不再按 `references/Project_R ...` 查找 PRD、开发流程和业务工作流清单。当代理工作规则发生变化时，更新 `AGENTS.md`；当产品范围或阶段任务变化时，同步更新 PRD 或开发流程。涉及前端视觉、控件状态、颜色、圆角、阴影、输入区或设置页的改动，必须先查看 `docs/ui-design-language.md` 并复用既有 token；除非同步更新该文档，否则不得临时新增一套 active / hover 视觉语言。

## 当前项目状态

- Phase 1-8 已完成。
- Phase 9 聊天主界面已完成视觉重构（Proma 双卡片布局）及增强功能（工作区选择器、多标签页、快速笔记、右键菜单置顶/重命名/归档、侧栏收起、搜索弹窗、归档管理、通知+蒸馏后端桩、软件内窗口控制按钮）。
- Phase 9B + P9 工作区文件管理竖切片已实现：Proma 侧栏细节修正、右上角置顶/双对话左右并排入口、项目文件/提示词/Skills/引用来源右侧常驻工具面板、输入框底部模型选择入口、三来源提示词调用面板、会话级 system prompt、用户本机提示词 `userData` JSON 存储、置顶后端持久化、Chat/Agent 空状态分离、Agent 工作区文件面板、多文件上传、100MB 单文件限制、删除进入回收区、恢复/永久删除、成员/管理员权限、审计日志、项目资料索引 pending/indexed 状态与当前项目资料召回。项目 GBrain 一键录入已补异步队列、复杂 PDF/图纸、图片/截图 MiMo 提炼、MP4 自动/长视频分段转写、说话人/术语纠错、EML 提炼、EML 附件递归和引用定位 MVP；文件预览、更细的 Office/PDF/图片/音视频质量回归后续补齐。
- Phase 10 旧 RAG / Wiki Router 已从正式主路径清退：`backend/knowledge_base/wiki/`、Chroma 与 `backend/vector_store/` 不再是正式知识库路径，也不作为 fallback；旧 `core/wiki_router.py`、`core/rag_engine.py` 及对应旧测试已删除。正式知识库问答采用显式路由，只有 `/query ...` 或等价知识库 Skill 调用 GBrain；普通 Chat 不自动查 GBrain，仍保留 chatbot 能力。前端已支持基础 Markdown 渲染与代码块复制；GBrain 引用来源以正文标签和来源列表按钮打开右侧 Markdown 片段预览面板。
- 2026-05-28 GBrain 知识库重构方向已确认，2026-05-30 原始文件提炼边界已收紧：GBrain 作为 Project_R 知识库内核，Project_R 作为公司业务入口、权限审计、原始资料保管、原始文件提炼、知识审核和可视化工作台。旧 `knowledge_base/wiki`、Wiki Router、Chroma 与 `vector_store` 不作为回退层或迁移目标；软件仍在代码阶段，旧 RAG 主路径可在 GBrain 接入时直接废弃，由管理员重新投喂源文件生成 `company-wiki`。Project_R 后端统一使用 `workspace_data/` 作为资料源根目录，不额外新增同级 `knowledge_sources/`；管理员将公司全局知识库源文件放入 `workspace_data/global/company-wiki/raw/`，Project_R Agent / Skills 按文件格式提炼为可审核 Markdown 后写入 `workspace_data/global/company-wiki/derived/`，`derived/` 直接作为 GBrain `company-wiki` source repo，不另建一套 GBrain repo 再同步，并启用本地 Git 版本记录用于审计、对比和回滚，不默认配置远程仓库或上传 GitHub；摄取状态、错误和来源映射保存在 `workspace_data/global/company-wiki/manifests/`。DeepSeek 负责文字类原始资料提炼，MiMo 负责 DeepSeek 不支持或不可靠的视觉/版式/图片类资料提炼，API Key 统一使用 Project_R 后端 Chat/LLM Provider 配置；用户只触发录入，不选择 API Key，Project_R 后端必须先识别文件类型和复杂度，再自动选择 DeepSeek、MiMo、转写流程或 `pending_extractor_capability`。GBrain 只接收 Project_R 产出的 Markdown，并负责 source sync/import、chunk、embedding、query、think、citation、graph、timeline、maintain、jobs、contradiction 等后 Markdown 知识库流程。Project_R 第一版正式业务采用 GBrain HTTP/MCP 常驻服务 + 后端 service account adapter，CLI 只用于开发期初始化、诊断、人工运维和应急排障。`/query` 是软件内“查询知识库”Skill 调用指令，普通 Chat 保持 chatbot 能力，不自动查询 GBrain；项目复盘、资料提炼、知识审核和纠错由独立 Project_R Skill 或管理员任务承接。第一阶段文件类型验证顺序为 Markdown / txt → PDF 结构化提炼 → 会议转写文本 → 录音 → 图片 / 截图 → 邮件导出；PDF 默认不再走纯文本抽取直接入库，必须通过模型/视觉辅助结构化提炼后再进入 `derived/`。所有进入 GBrain 查询面的提炼型 Markdown 必须遵守 `bilingual_zh_en_aligned`：无论原始资料是中文、英文还是中英混合，最终知识页都要中英文并存且表达同一事实，不能出现中英文信息不对称；原始 source record 可保留原语言。当前矩阵文档为 `docs/gbrain-feature-inventory.md`，具体导入/提炼/审核/索引流程见 `docs/gbrain-ingest-workflow.md`，原始文件提炼边界 ADR 为 `docs/adr/0009-pr-owned-extraction-to-gbrain-markdown.md`，自动分类与模型路由 ADR 为 `docs/adr/0011-automatic-extractor-routing-by-file-type.md`。项目资料后续沿用 `workspace_data/project/{品牌}/{项目代号}` 上传入口，再映射到独立项目 source。
- 2026-05-30 source scope 审核规则已确认：管理员后台录入公司知识视为管理员已自行检查，不需要额外审核；用户私人空间附件不得进入公司知识库；项目工作区文件由用户在项目文件面板点击“一键录入项目知识库”后只进入当前项目 source，不流入公司公用知识库，不需要管理员审核，完成或失败后通知点击录入的用户。“未入库文件”的产品定义覆盖当前项目内所有知识目标文件类型，包括 Markdown/txt、DOCX、PDF、复杂 PDF、音频/视频、图片/截图、邮件和未来支持的业务附件；文件只有在 Project_R 成功提炼成 source-scoped Markdown 且 GBrain 已同步到当前项目 source 后才算已入库。第一版一键录入处理当前项目所有当前可处理且尚未入库的文件，并显示待录入数量，例如“录入 12 个未入库文件”；不做逐个文件选择。2026-05-31 项目 source 已补图片/截图、长视频分段转写、说话人/术语纠错和 EML 附件递归 MVP；暂未完成的批量邮件线程合并、置信度、绝对时间戳回链、区域级图片引用和文件预览 UI 仍要保留为后续项。审核队列保留给答案低分反馈、纠错、显式提升公司知识和异常情况。决策文档为 `docs/adr/0010-source-scoped-knowledge-ingest-review-policy.md`。
- 2026-06-01/06-02 客户情报 / 客户画像方向已确认并收紧：客户画像是“受限业务情报 source”，不是公司公共知识库，不得写入 `company-wiki`；客户知识库只有一个统一受限 source，即当前 `customer-reference`，所有客户信息在同一客户库内共存，不再按每个客户拆 GBrain source。Project_R 负责客户工作区权限入口：系统管理员可新建“客户情报”工作区，默认隐藏；普通用户只有作为成员或授权组别时才能搜索/进入。客户工作区 `/query` 必须先通过 Project_R 权限判断，再显式路由到 `customer-reference`，不得回落到 `company-wiki`；验收重点是同一客户库内查询 5Points、18 Mary Avenue、Aaron Morris 等特定客户/项目/联系人时，答案和 citation 不混入其他客户资料。图片、ZIP、Excel 等客户复杂资料在当前 goal 中只标记 `pending_extractor_capability`，不得污染 GBrain；复杂客户资料 extractor 等 Gary 提供真实样本后另开目标。工作区图谱、实体候选、native graph/timeline/backlinks、Timeline 折叠/密度切换、大画布和安全源文件预览已有 MVP，但后续仍需自动布局优化、native timeline 可视化增强、正文级实体合并/删除和客户/项目/company 联合查询边界。
- 2026-06-02 工作区权限已调整为开放项目优先：系统管理员账号可新建项目工作区，并可进入全部项目/客户类共享工作区但不必写入 `WorkspaceMember`；用户默认私人空间只归本人可见，系统管理员列表不展示、也不能直接打开其他人的私人空间。公司项目默认对所有有效用户开放，所有用户可搜索、进入和使用项目资料；只有被设置为隐藏项目后，才限制为系统管理员、项目成员白名单和授权组别可搜索/进入。工作区 `admin` 是 scoped admin，只在该工作区拥有成员管理、隐藏/开放项目、重命名项目、删除/恢复他人文件、较大上传额度等权限，不等同于系统管理员。成员管理不挂载在项目文件面板中，当前入口为工作区列表中可管理项目的盾牌按钮，点击后打开独立成员管理抽屉；后端接口为 `POST /workspaces/{id}/members`、`PUT /workspaces/{id}/members/{user_id}`、`DELETE /workspaces/{id}/members/{user_id}`、`POST /workspaces/{id}/groups`、`DELETE /workspaces/{id}/groups/{group_name}`。
- 2026-06-02 用户确认客户复杂资料 extractor 暂时从当前 GBrain 产品化 goal 取消：图片、ZIP、Excel 等客户复杂资料在当前目标中只要求继续标记 `pending_extractor_capability` 且不得污染 GBrain source；等 Gary 提供真实样本后再另开目标补齐。
- 2026-05-29 GBrain 正式接入切片已实现：`core/gbrain.py` 支持 GBrain 配置读取、`workspace_data/global/company-wiki/{raw,derived,manifests}` 目录初始化、`derived/` 本地 Git 初始化、service account token 隐藏、GBrain `/health` 探测、MCP `sources_list` / `sources_status` / `sync_brain` / `run_doctor` / `get_status_snapshot`、`query(..., source_id=company-wiki)` adapter、后端启动/重启 GBrain HTTP 服务、service process record、readiness 错误提示，以及 `/health/gbrain` 和 `/admin/knowledge/status` 管理状态入口。本机已用 `GBRAIN_HOME=workspace_data/global/company-wiki` 初始化 GBrain PGLite brain，并将 `company-wiki` source 注册到 `workspace_data/global/company-wiki/derived/`；`scripts/start-gbrain.ps1` 可启动/重启 `gbrain serve --http --port 3131 --bind 127.0.0.1`，并会清理 stale PGLite lock / postmaster 状态。2026-05-29 已切换到本地免费 embedding：Ollama + `mxbai-embed-large`，GBrain 配置为 `model=ollama:mxbai-embed-large`、`dimensions=1024`、`semantic_search_ready=true`。Gary 放入的真实样本已完成第一轮验证：4 个 Markdown、1 个 DOCX、2 个 PDF 曾成功编译为 7 个 `derived/` Markdown，1 个 MP3 因未配置转写被 manifest 标记为 skipped；该轮 PDF 结果属于质量验证，不代表 PDF 纯文本抽取被接受为长期入库方案。2026-05-29 已清退两个 PDF 纯文本页面并完成 PDF 结构化提炼 MVP：新增 `core/pdf_structured_extraction.py`，PDF 默认仍不纯文本直入库，显式启用后用全文文本 + MiMo V2.5 关键页 PNG 视觉辅助生成 `pending_review` Markdown 到 `derived/.pending_review/`，管理员通过知识审核后再提升到可同步的正式 `derived/` 路径；PDF 同名 PNG 文件夹作为视觉侧车资料，不作为独立 raw 文件扫描；提炼输出已按 `bilingual_zh_en_aligned` 重跑为中英文对齐版本，本次 AS 1288 / AS 2047 样本已标记为 `review_status: approved` 后进入查询面。当前 manifest 为 `total=9`、`compiled=7`、`skipped=2`、`failed=0`，2026-05-30 PGLite 重建并重新 sync 后 `page_count=7`、`chunks_total=207`、`chunks_unembedded=0`，已生成真实 1024 维向量；为适配 `mxbai-embed-large` 较短上下文，本地 `reference/gbrain-master` 已对 Ollama recipe 和 Markdown chunk hard cap 做保守调整。Project_R 正式 `/query` 路径已通过 `core/knowledge_sources.py` 调用 GBrain `company-wiki` / 项目 source，不再使用 WikiRouter / RAGEngine / Chroma fallback；管理员后台可展示 service health、source 注册状态、embedding provider、semantic readiness、page/chunk 数、manifest、sync 和 doctor 摘要，并提供启动/重启 GBrain、导入 raw、含 PDF 提炼按钮。2026-06-01 起 `/query` 已提升为 GBrain native `think` 主路径；reranker 和完整端到端 UI 手工验收仍是后续项。
- 2026-05-30 已建立 GBrain 查询质量回归集第一版：`backend/tests/fixtures/gbrain_query_regression_cases.json` 固定 AS 1288、AS 2047、VMU、0515 会议、书面化原则等真实问题与期望来源；`backend/tests/test_gbrain_query_regression.py` 覆盖离线 adapter 排序逻辑；`backend/scripts/gbrain_query_regression.py` 可验证本机 GBrain service、Ollama embedding 与真实 `/query` 命中。为通过回归，`core/knowledge_sources.py` 增加了规则类 query expansion、中文规则/流程类标题化查询变体、`rules/` 来源加权、精确标题命中加权和会议噪声惩罚；PGLite 重建后 `书面化原则是什么` 已再次回归并稳定首位命中 `rules/书面化原则`。管理员后台已新增 `POST /admin/knowledge/regression` 和前端“查询回归 / Think 回归”按钮，默认只跑 query，显式选择时才调用 DeepSeek-backed Think 回归；2026-06-02 起回归结果会保存到 `manifests/gbrain-quality-reports.json`，并在 `/admin/knowledge/status` 与管理员 GBrain 面板展示最近质量报告、最近 5 次趋势和 JSON 导出按钮。后续新增 GBrain 检索、chunk、embedding、PDF 提炼或升级上游时，必须同步扩展并运行该回归集。
- 2026-05-31/06-01 项目级 GBrain source 一键录入真实样本闭环已扩展：每个项目工作区动态映射为稳定 source id `project-{brand}-{workspace_id}`，路径为 `workspace_data/project/{品牌}/{项目代号}/derived/`，默认 `--no-federated`；`core/gbrain.py` 支持项目 source registration plan/status/ensure/sync，`core/knowledge_sources.py` 对项目查询显式传入项目 source id 并补项目内引用定位，`/admin/knowledge/status` 返回 `project_sources`。2026-06-01 已补项目 source 专属 Think OAuth client manifest：`workspace_data/global/company-wiki/manifests/gbrain-think-source-clients.json`，项目 `project-*` source 可自动注册/复用 `gbrain auth register-client --source <source> --federated-read <source>` 生成的 token-bound client；项目一键录入在 sync 成功后预先准备该 client，并返回 `gbrain_think_status`，避免项目 `/query` 因未列入 `GBRAIN_THINK_ALLOWED_SOURCES` 被拒绝。新增 `core/extractor_classifier.py`，项目录入前输出 `source_scope`、`file_kind`、`extraction_complexity`、`extractor_profile` 和 `classifier_reason`；明显建筑图纸/总平/楼层/Rev 图纸包即使可抽文字，也路由到 `vision_required` / `mimo_vision`，避免图纸碎片文字误入库。`core/gbrain_project_ingest.py` 扫描项目文件目录并排除 `derived/`、`manifests/`、`.trash/`、`.git/` 和 PDF 侧车图片目录，将 Markdown/txt、DOCX、普通 PDF、复杂 PDF/图纸、图片/截图、MP4 自动/长视频分段转写会议、EML 邮件线程和 EML 附件递归编译到项目 `derived/`。项目 pending review 不再作为默认路径；`POST /workspaces/{id}/knowledge/ingest` 会同步 project source、按 sync 结果更新 `rag_status`，`POST /workspaces/{id}/knowledge/ingest/async` 已支持后台 job 队列，完成或失败后通知点击用户；前端项目文件面板一键录入默认排队并轮询。真实样本 `backend/workspace_data/project/BFI/GBrain验收项目-001/` 增量验收结果：11 个文件全部编译，`total=11, compiled=11, pending_extractor_capability=0, pending_transcription=0, failed=0`；长视频分 11 段转写并生成说话人/术语纠错 transcript，截图 `审批流程规则.png` 已生成项目 Markdown，Lucerna 邮件 4 个 PNG 附件已递归编译。
- 2026-06-01 GBrain 早期测试数据已按 Gary 确认清退：`company-wiki` 的测试 `raw/derived/manifests` 与测试期 `workspace_data/project/` 已备份到 `backend/workspace_data/_backups/gbrain-reset-20260601-140029/`，GBrain 中 `company-wiki` 保留 source 与 OAuth client 绑定但已清空 pages/chunks/embeddings/query cache，测试项目 source `project-bfi-2`、`project-bfi-6` 已删除。随后 Gary 将 Notion 导出的真实公司知识 Markdown 放入 `backend/workspace_data/global/company-wiki/raw/`，并确认不需要保留清洗前源文件副本；已新增并执行一次性清洗脚本 `backend/scripts/clean_notion_markdown_once.py`，281 个 Markdown 全部移除旧 frontmatter，移除 44 个图片/Obsidian embed、6 行 Notion/外链噪音、501 个旧分隔线。`compile_company_wiki_sources()` 成功编译 281/281，GBrain full sync 成功导入 `page_count=281`、`chunks_total=1892`、`chunks_unembedded=0`、embedding 覆盖率 100%；Project_R 正式查询路径抽验 `书面化原则是什么`、`VMU 标准作业流程`、`项目邮件相关规则` 均首位命中正确 source。本轮是 Notion 旧格式清洗 + 原生 Markdown 入库，不是 DeepSeek 全文中英双语重写；项目 source 仍为空，等待 Gary 新建测试专用项目重新验收。
- 2026-05-30/06-01 GBrain `think` 已完成 guarded adapter 第一版并提升为 `/query` 主路径：`core/gbrain.py` 支持 source-scoped OAuth client_credentials 后调用 MCP `think`，`api/chat.py` 将 `/query ...` 收紧为唯一知识库问答入口并直接调用 GBrain native `think`，不再提供 `/query --quick`、`/query --think` 或 `/think` 两套用户模式；`core/knowledge_sources.py` 会把 citations 归一化为聊天来源项，并把 gaps、conflicts、warnings 写入 `context_trace.gbrain_think` 供前端“本轮上下文”展示。2026-06-02 已补 GBrain Think 缺口/冲突审核提交 MVP：用户可从带 gap/conflict/warning 的 `/query` 回答提交 `gbrain_think_review:*` 知识审核项，管理员后台复用现有知识审核与 citation-fixer 入口。同日已补 GBrain 查询/Think 质量报告存档、趋势和导出 MVP：`POST /admin/knowledge/regression` 保存最近报告，管理员 GBrain 面板显示 query/think 通过数、失败用例、preflight 错误、最近 5 次趋势，并可按报告 ID 导出 JSON。`patches/gbrain/0003-think-source-scope-gather-and-takes.patch` 已让上游 `runThink()` -> `runGather()` -> hybrid/takes/graph 检索流传递 source scope，并让 PGLite/Postgres takes keyword/vector SQL 过滤 `pages.source_id`；GBrain `bun run typecheck` 与 `bun test test/takes-engine.test.ts test/think-pipeline.serial.test.ts` 已通过。已创建 `company-wiki` source-scoped OAuth client并跑通真实 MCP `think`，确认 `status=ok` 且 token-bound source scope 生效；配置 `GBRAIN_THINK_MODEL=deepseek:deepseek-chat` 后，`书面化原则是什么` 可返回 DeepSeek 综合答案、`warnings=[]` 和 citation。项目 source 已补自动 source-scoped Think OAuth client 准备能力；`backend/scripts/gbrain_think_regression.py`、`backend/tests/fixtures/gbrain_think_regression_cases.json` 与 `backend/tests/test_gbrain_think_regression.py` 已固定第一条真实服务/离线验收。更多项目/客户 source 真实回归仍需继续补齐。
- 2026-05-31 音视频会议提炼已完成项目自动转写 MVP 并补长视频分段/说话人/术语纠错：新增 `core/meeting_structured_extraction.py` 和 `core/media_transcription.py`，company-wiki 与项目 source ingest 均支持 MP3/MP4/MOV/MKV/WEBM 搭配同名 `.transcript.*`、`.vtt/.srt` 或同名目录 `transcript.*`，生成 `meeting_structured_extract` + `bilingual_zh_en_aligned` Markdown；项目 MP4 无 transcript 时会用本地 ffmpeg 抽音频并调用 MiMo 自动转写，长媒体默认 300 秒分段，再用 DeepSeek profile 输出 `Speaker Map`、纠错后 transcript 和术语纠错记录。company-wiki 会议直入规则仍需后续收紧。manifest 记录 transcript 文件、转写 provider/model、转写分段数、refinement provider/model、术语表、行动项/决策/风险候选数量和 `transcription_status`。置信度、绝对时间戳回链、专业 diarization 和真实音视频质量回归仍未完成。
- 2026-05-30 GBrain 维护任务已完成第一版竖切片：`core/gbrain.py` 包装 GBrain MCP `run_onboard(mode=check)`、`list_jobs`、`submit_job`、`get_job`、`get_job_progress`、`cancel_job`、`retry_job`、`find_contradictions`；管理员后台新增“GBrain 维护”页，显示 doctor/maintain/jobs/contradiction 状态，可提交 `sync/embed/lint/backlinks` 白名单任务并取消/重试；任务操作写审计日志并通过通知中心打开管理员 GBrain 维护页。答案反馈纠错审核 MVP 已接入：用户对带 GBrain 引用来源的回答打低分时，系统会生成 `gbrain_answer_correction:*` 知识审核项并通知管理员。citation-fixer 已确认是 GBrain agent skill，不是普通 job，后端已补 `submit_agent` / `submit_citation_fixer` 与 `POST /admin/knowledge/gbrain/citation-fixer`，前端管理员 GBrain 维护区已补提交表单；`agent_status` 会区分 `disabled/oauth_required/configured_unverified/ready`，并额外显示 `binding_status=not_verified/submit_verified/inline_execution_verified/execution_verified`。新增 `backend/scripts/gbrain_agent_preflight.py`、`backend/scripts/gbrain_register_agent_client.py`、`backend/scripts/gbrain_enable_agent_gateway_loop.py`、`backend/scripts/gbrain_agent_submit_smoke.py`、`backend/scripts/gbrain_agent_inline_execution_smoke.py`、`backend/scripts/gbrain_agent_citation_fixer_mutation_smoke.py` 和 `docs/gbrain-agent-citation-fixer-runbook.md`；`patches/gbrain/0004-agent-bound-oauth-client-registration.patch` 已补齐 GBrain 本地 `auth register-client --bound-*` 注册入口。本机已完成真实 agent-bound OAuth client 注册、`agent.use_gateway_loop=true` 配置、`submit_agent` 绑定冒烟、PGLite `jobs submit subagent --follow` 只读 inline 执行烟测，以及 2026-06-02 citation-fixer 真实改写型 smoke：job #172 将 `reviews/citation-fixer-smoke/project-r-citation-fixer-smoke` 的坏引用修复为 `[[rules/书面化原则]]`，脚本把 GBrain `.sources/company-wiki/...` sidecar 同步回正式 `derived/` 文件并提交本地 Git `8a3ace3`，预检显示 `GBRAIN_AGENT_EXECUTION_VERIFIED=true` / `status=ready`。同日继续补 `core/gbrain_citation_fixer_jobs.py`、`gbrain-citation-fixer-jobs.json` manifest 和 `POST /admin/knowledge/gbrain/citation-fixer/poll-jobs`：管理员提交 citation-fixer 后可追踪 GBrain job，终态完成时将 `.sources/company-wiki/...` sidecar 同步回正式 `derived/`、提交本地 Git、写审计并通知管理员。随后 `core/gbrain_maintenance_worker.py` 已把 citation-fixer poll 纳入 Project_R 维护 worker，管理员 GBrain 面板显示追踪任务和 worker 最近轮询结果，并提供“轮询引用修复”按钮。随后补 `POST /admin/knowledge-reviews/{review_id}/citation-fixer` 与知识审核表格“引用修复”按钮：管理员可从 `gbrain_answer_correction:*` 低分审核项受控提交 citation-fixer，审核项保持 pending，不自动通过、不自动覆盖事实。随后补 `POST /admin/knowledge/gbrain/citation-fixer/{job_id}/rollback` 与 tracking 列表“回滚”按钮：管理员可撤销单个 citation-fixer job 的 Git 写入，系统写审计/通知并清理 sidecar。随后补 `core/gbrain_contradiction_probe.py`、`gbrain-contradiction-probe.json` manifest、管理员配置/手动运行/到期检查接口和面板，并把 contradiction probe tick 纳入 `core/gbrain_maintenance_worker.py`：Project_R 用受控查询列表调用 GBrain 原生 `eval suspected-contradictions run` 生成疑似冲突，运行/失败写审计和通知。随后补 worker 异常通知/审计：维护 tick 抛异常时写入 `last_error`、通知系统管理员并生成 `gbrain_dream_cycle_worker_error` 失败审计。未完成：GBrain 原生 Postgres worker 长跑、批量 citation-fixer 费用/权限边界、复杂恢复策略、自动 remediation 费用/权限边界；contradiction probe 只读发现疑似冲突，不自动覆盖事实，且 GBrain CLI 当前缺少显式 source scope 参数。
- 2026-06-02 管理员 GBrain 维护区已补 Worker 诊断卡，直接展示 Project_R 维护 worker 的启停、心跳、运行次数、最近错误、Dream tick/poll、citation-fixer poll 和 contradiction probe 最近状态；该卡只读，用于排障，不替代通知中心和审计日志。同日已建立正式 worker 策略文档 docs/gbrain-worker-strategy.md，确认当前采用 Project_R worker + PGLite inline，暂缓 GBrain 原生 Postgres worker。Dream Cycle / contradiction probe 默认关闭（管理员手动开启），citation-fixer 必须管理员手动提交（不允许自动改写公司知识），contradiction probe 只读不写；所有 worker 异常通过通知中心和审计日志可追踪。，直接展示 Project_R 维护 worker 的启停、心跳、运行次数、最近错误、Dream tick/poll、citation-fixer poll 和 contradiction probe 最近状态；该卡只读，用于排障，不替代通知中心和审计日志。
- 2026-05-30 GBrain 上游源码维护原则已确认：Project_R 将 GBrain 视为外部上游组件，正式运行通过 Project_R 后端 adapter 调用 HTTP/MCP/CLI 服务；后续不得无记录地直接修改 `reference/gbrain-master`。优先使用 GBrain 原生配置/command/operation/skill/recipe/schema、Project_R adapter、以及更好的 `derived/` Markdown 结构解决问题；确实绕不开的 GBrain 源码改动必须记录到 `patches/gbrain/`，或升级为明确的 Project_R fork/submodule。当前 Ollama recipe、recursive chunker、think source-scope、agent-bound OAuth client 注册、subagent tool source scope、AI SDK v6 tool schema/message 兼容、Think 中文标题式问题 gather 变体七处本地改动已记录为 `patches/gbrain/0001-ollama-local-embedding-limits.patch`、`patches/gbrain/0002-recursive-chunker-local-ollama-cap.patch`、`patches/gbrain/0003-think-source-scope-gather-and-takes.patch`、`patches/gbrain/0004-agent-bound-oauth-client-registration.patch`、`patches/gbrain/0005-subagent-tool-source-scope.patch`、`patches/gbrain/0006-chat-tool-json-schema-wrapper.patch`、`patches/gbrain/0007-think-gather-title-query-variants.patch`；升级 GBrain 前必须审计、重放或退役这些 patch，并跑 GBrain sync/query/think/agent 回归。
- Phase 10C 会话临时附件已扩展：支持附件按钮选择、剪贴板粘贴和拖拽到对话区，图片/PDF/通用文件可作为当前会话临时附件保存；文本类附件与可提取文本的 PDF 会注入 LLM 上下文；图片附件在支持图像输入的 MiMo 模型下会以多模态 content block 投递给模型，DeepSeek 等不支持多模态的模型会提示切换模型。会话超过 3 天未活跃后自动清理临时附件，删除会话时同步清理；会话附件向量化/分块检索、复杂预览和附件引用定位后续补齐。注意：项目知识库 ingest 已有图片/截图提炼和 EML 附件递归，和会话临时附件不是同一条链路。
- 全局底层规则文件已预留：`backend/prompt_presets/global-base-prompt.md`，初始为空。后端每次组合 Chat/Agent system prompt 时都会优先读取该文件；内容为空则不影响现有行为，内容存在时优先级高于会话提示词、附件和知识库/项目资料。
- Phase 10E 工作区文件管理已完成 P9 竖切片，图谱自动布局优化与 Timeline 时间轴可视化增强已于 2026-06-02 完成：力导向布局改为 BFS 排序初始化 + 实体类型聚类吸引 + 12 轮自适应 cooling；canvas 节点按 entity_type 着色（客户紫色、项目橙色、事件红色等）；新增时间轴模式作为 Timeline 密度切换的第三档，以线性时间线展示事件、hover/click 联动图谱节点。图谱权限已通过 _ensure_can_open_workspace 保护 customer workspace，未授权用户无法打开客户工作区图谱。：成员可上传多文件、新建文件夹、删除自己上传的文件并进入回收区，工作区管理员可删除所有文件；支持恢复/永久删除、审计日志、路径逃逸防护、项目索引状态刷新、文件预览侧窗、单项剪切 / 复制 / 粘贴和单项拖拽移动，用户侧已退役“移动到路径”输入且第一版不做多选。项目对话已接入当前项目 GBrain source；一键录入已支持异步队列、复杂 PDF/图纸 MiMo 视觉提炼、图片/截图提炼、MP4 自动/长视频分段转写、说话人/术语纠错、EML 邮件线程提炼、EML 附件递归和项目引用定位。更完整的项目质量回归后续补齐。
- Phase 11 文件生成已完成第一条 tracer bullet：后端保留 `document_generation` 渲染基础 `.docx` 的能力，前端可显示下载卡片并通过权限校验接口下载；管理员过期清理接口已实现。当前显式路由阶段，普通自然语言不再自动命中 `document_generation`，后续待文件生成入口或 Skill 完整后再恢复“Chat 发现意图”。正式模板、复杂错误处理与人工打开验收后续补齐。
- Phase 12 业务 Skill 已完成底座；早期 U03 标签打印 tracer bullet 已确认退役，不再作为 Skill 样板、测试目标或业务能力示例。`SkillRun` 表、`core/skill_runner.py` 元数据加载/匹配/启动/补参、`core/skill_execution.py` 执行输出、`api/skills.py` 列表/匹配/启动/补参/查看/reload 接口已实现；当前显式路由阶段，用户必须通过前端 Skill 面板或 `selected_skill` 显式启动 Skill，不再由自然语言自动触发。会话中存在收集中的 SkillRun 时，后续用户消息仍可作为对话式补参，前端已显示 Skill 运行卡片和文件卡片。下一步以真实业务 Skill 做端到端 UI 验收。
- Phase 13 管理员后台 MVP 已完成可用入口：用户列表/新增/禁用/角色修改/重置密码、GBrain 知识库状态/刷新、审计日志按用户/日期筛选、知识审核查看/通过/驳回/修改后通过、模板与 Skill 状态只读接口已实现，普通用户受 403 保护；`User.is_active` 会阻止禁用账号登录。审核通过的普通候选知识写入 `workspace_data/global/company-wiki/derived/reviews/知识审核沉淀.md` 并触发 GBrain sync；PDF 等 `gbrain_pending_review:*` 候选会从 `derived/.pending_review/` 提升到正式 `derived/` 路径后再进入查询面。设置页已显示管理员专属区。审计导出和真实 UI 验收后续补齐。
- Phase 14 设置界面已完成主体：左侧分类导航 + 右侧内容区已接入通用、服务器、提示词、归档、Agent、Chat 工具、远程连接、教程、快捷键、管理员分类；昵称/头像标识可通过 `PUT /auth/me` 更新；通用偏好、主题、Chat 工具、钉钉配置、快捷键使用本地 `localStorage` 保存；提示词管理复用公司预设接口与 Electron 本机用户提示词 IPC。联网搜索真实能力、钉钉 Bot 链路、快捷键全局绑定后续补齐。
- Phase 15 欢迎引导已完成代码级第一版：首次启动进入 `/onboarding`，支持欢迎页、教程页、后端 `/health` 环境检测、服务器地址保存与跳过；清除本地配置后的 Electron 重启验收待 Gary 手工确认。
- Phase 16 钉钉 Bot 已按 Gary 2026-05-21 决策调整为后补功能，当前仅保留设置页远程连接占位，不作为阶段推进阻塞项。
- Phase 17 Windows 联调已完成静态检查底座：`scripts/test-windows.ps1` 检查 Windows 绝对路径硬编码、前端后端地址硬编码和配置入口；`docs/test-windows.md` 记录本次代码级检查结果。真实 Chat/RAG/文件生成/Skill/管理员后台全链路仍需手工运行补截图与时长。
- Phase 18 异步通知中心 MVP 已完成代码级实现并通过本机验证：通知模型采用 `category + severity + action_status + action_kind/action_payload_json`，旧 `type` / `link` 仅兼容；广播通知展开为每个用户的通知记录；前端入口位于侧栏底部设置图标左侧，使用 360px 左下 Popover；第一版采用 60 秒短轮询，不引入 WebSocket/SSE；触发源已接入 Skill/文件生成、知识审核、工作区权限与索引、风险告警最小桩。
- Phase 19 Mac mini 迁移因机器尚未准备到位而暂缓，近期执行顺序中跳过；Phase 20 客户端打包与内网更新的代码级准备不得以 Mac mini 迁移完成为前置条件。
- Phase 20 客户端打包与内网更新已完成代码级准备并通过本机验证：Windows 安装包由 Project_R 后端在公司内网分发，不默认依赖 GitHub Releases；更新可用性按当前客户端版本检查，通知中心仅显示客户端版本检查产生的新版本入口；真正下载、校验和启动安装器由 Electron 主进程/安装器负责，renderer 不得直接覆盖应用文件。更新交互采用“发现新版本 → 显示更新日志 → 下载进度窗口 → 更新已就绪 → 重启安装”流程；自动更新失败时提示联系管理员获取最新版安装包。管理员后台已提供更新包上传/登记入口；`bun run dist:win` 已生成 `frontend/release/Project_R-Setup-0.1.0.exe` 与 `frontend/release/Project_R-Setup-0.1.1.exe`，并已通过本机静默安装升级验证。另一台 Windows 安装测试和正式更新仓库登记仍未完成。
- V3.0 Proma shell 重构方案已确认（历史方案文档如仓库内存在则以该文档为准）：最高原则为 Proma shell first, Project_R core always；V3.0-A 先做侧边栏、标签页、设置弹窗、Welcome/登录、Chat/Agent 姿态、`/` Skill 候选等壳层体验，工作区后端模型、回收站、文件拖拽、附件扩展、空间报警和管理员后台完整重构放后续阶段。
- V3.0-A 登录页已按 animatedlogin-main 参考完成动态角色动画重构（2026-05-22）：左右分栏布局，左侧灰色渐变 + 4 个卡通角色（紫/黑/橙/黄），支持鼠标跟随眼球、随机眨眼、输入聚焦互动、登录失败摇头动画；右侧纯白表单区含密码可见性切换与悬停滑出按钮。已取消 Privacy Policy / Terms of Service / Contact / Google 登录 / 忘记密码 / 注册入口。Welcome 页已添加流动极光 CSS 背景动画。
- **2026-05-22 UI/UX 优化归档**（防止后续回退）：
  - 登录页新增「记住账号」与「记住密码」复选框：账号自动填充，密码以 `btoa(encodeURIComponent(...))` 编码后存 `localStorage`，下次启动自动回填。
  - 设置弹窗左侧导航图标与文字对齐方式改为 `grid-template-columns: 24px 1fr`，图标统一放大至 20px，解决反复出现的错位问题。
  - 聊天发送按钮取消 `SENDING_LABELS` 四词循环；loading indicator 迁移到对应会话的消息列表底部 AI 占位卡片，发送中按钮位置使用停止图标并支持 Esc 中止当前会话请求。
  - AI 占位卡片使用 Loading.css 风格四色环 SVG 动画（红/橙/蓝/粉，尺寸缩至 1.6em），搭配 20 个 whimsical 词汇（Discombobulating / Concocting / Moonwalking / Mulling / Purring / Doodling / Pondering / Exploring / Discovering 等）每 2 秒随机切换且不连续重复。
  - 用户消息气泡底部操作工具栏改为右对齐（`.message-row-user .message-actions { justify-content: flex-end; }`），与左侧 AI 消息形成视觉区分。
  - 工作区排序从上下箭头按钮改为 HTML5 拖拽排序（`draggable` + `dragIndex` state + `localStorage` 持久化 `project_r_workspace_order`），默认工作区禁止删除但可拖动。
  - 侧边栏用户头像取消统一背景蒙版：emoji 或图片头像直接展示，仅文字首字母头像保留背景色（通过条件类名 `.sidebar-user-avatar.is-text` 控制）。
- **2026-05-27 模型 / 提示词 / 暗色主题优化归档**（防止后续回退）：
  - 模型选择从单一 provider 下拉升级为后端白名单 `model_profile`：同一组 DeepSeek Key 可跑 DeepSeek Flash / Pro，同一组 MiMo Key 可跑 MiMo V2.5 / V2.5-Pro；前端只显示 `/health/llm` 返回的已配置模型 profile，不展示未配置占位项或 API Key。
  - 输入区“思考”按钮不再表示切换模型，而是向后端发送 `thinking` 布尔值；后端按 provider 生成实际参数：DeepSeek 使用 `thinking.type` + `reasoning_effort`，MiMo 使用 `thinking.type`。
  - 模型下拉、提示词面板、Skill 面板和输入区工具栏已按现代 Agent 组件重排：左对齐、自然文档流、无固定高度、无选项绝对定位，解决文字重叠和挤压；点击输入框附近空白处可关闭下拉面板。
  - RAG 来源右侧栏绑定当前会话，切换会话自动关闭；来源内容使用 Markdown 渲染，正文来源标签改为轻量 ghost tag。
  - 暗色主题已修复用户消息气泡、切换 Agent 提示气泡、公司预设提示词选中态、设置页开关按钮、AI Markdown 正文行高与段落间距。
  - 设置页头像选择器已限制 emoji 网格溢出，支持点击外部或按 Esc 关闭；管理员后台“用户管理”标签取消无意义用户数量 badge。
- 开发期后端默认地址：`http://localhost:8000`。
- 管理员账号：`admin / Project_R_2026`。

已验证的核心链路（chat 会话）：

- `GET /health`
- `GET /health/llm`
- `POST /auth/login`
- `GET /auth/me`
- `POST /chat/sessions`
- `GET /chat/sessions`
- `GET /chat/sessions/archived`
- `GET /chat/sessions/{id}`
- `PUT /chat/sessions/{id}`
- `DELETE /chat/sessions/{id}`
- `POST /chat/sessions/{id}/archive`
- `POST /chat/sessions/{id}/restore`
- `GET /chat/sessions/{id}/messages`
- `POST /chat/sessions/{id}/messages`

新增 API（workspace / notification / distillation，代码已就绪，待运行迁移后验证）：

- `POST /workspaces` / `GET /workspaces` / `GET /workspaces/search` / `GET /workspaces/{id}` / `POST /workspaces/{id}/join` / `DELETE /workspaces/{id}`
- `GET /notifications` / `POST /notifications/{id}/read` / `POST /notifications/read-all`
- `GET /distillation/suggestions` / `POST /distillation/suggestions/{id}/review`
- `GET /skills` / `POST /skills/match` / `POST /skills/runs` / `POST /skills/runs/{id}/inputs` / `GET /skills/runs/{id}` / `POST /skills/reload`
- `GET /admin/users` / `POST /admin/users` / `PUT /admin/users/{id}` / `GET /admin/audit-logs` / `GET /admin/knowledge-reviews` / `POST /admin/knowledge-reviews/{id}` / `GET /admin/templates`

## 项目结构

```text
Project_R/
├── .agents/skills/       # mattpocock/skills 已安装工程/生产力 skills
├── AGENTS.md             # Codex / 通用 Agent 工作规则
├── skills-lock.json      # skills 版本锁文件
├── backend/              # FastAPI 后端
├── frontend/             # Electron + React + Vite + TypeScript + Jotai 前端
├── docs/agents/          # Skill 设计规范、issue tracker、triage labels、domain docs
├── scripts/              # 项目维护脚本
├── Project_R PRD.md      # 产品范围、目标用户、长期能力边界
├── Project_R 开发流程.md # 阶段顺序、任务清单、完成标志、实现状态
└── Project_R 业务工作流清单.md # 企业业务 Skill 候选清单与实现状态
```

## 开发理念

Project_R 后续开发按“可验证竖切片”推进，而不是按目录堆功能。

1. 先让一个真实业务场景跑通，再扩展通用能力。
2. 后端是业务能力中心，前端是安全、轻量、可配置的桌面入口。
3. 业务层只依赖统一接口，不直接绑死某个 LLM 厂商、模板库或前端页面。
4. 每个阶段都必须有清晰完成标志；未验证的代码只能写实现状态，不能勾 checklist。
5. 默认优先做小型可运行测试，真实 LLM API 调用不进入默认单元测试。

四条长期主线：

| 主线 | 目标 |
|---|---|
| 对话底座 | 登录用户稳定发起、保存、恢复多轮对话 |
| 知识底座 | 系统能可信引用公司文档回答问题 |
| 文件与 Skill 底座 | 用户通过显式入口或后续自然语言意图识别生成标准业务文件或流程输出 |
| 管理与交付底座 | 管理员可维护系统，员工可稳定使用 |

## 开发红线

- 所有路径必须可迁移到 Mac mini，禁止写死 `D:/...`、`C:/...` 等绝对路径。
- 后端路径用 `pathlib.Path` 或跨平台路径 API；文本读写显式使用 `encoding="utf-8"`。
- 环境变量写入 `.env.example`；真实 `.env`、数据库、API Key、生成文件不入 Git。
- API Key 只允许存在于后端环境变量或服务端安全配置中，绝不进入前端、日志、响应体或文档示例明文。
- 前端请求层不得写死 `localhost` 或 `127.0.0.1`；后端地址由 `server-atoms.ts` 管理并持久化，开发默认值来自 `VITE_DEFAULT_API_BASE_URL`。
- 员工前端不得暴露 API Key 或多 Key 配置；允许提供受后端白名单约束的模型/Provider 路由选择入口，用于后续本地敏感模型与云端模型切换。
- Proma 参考资源（如仓库中存在的历史参考目录）是 Project_R 初步雏形阶段的 UI shell 参考基座。Gary 提到“参考 Proma”时，默认含义是参考 Proma 的局部界面表现、信息分区与交互节奏，不默认表示迁移 Proma 的底层架构、客户端执行链路或安全模型。
- Proma 参考必须按三层判断：
  - **表现层**：布局、圆角、间距、图标位置、按钮形态、空状态文案结构、侧栏收放方式、会话列表质感、标签页表现等，默认允许强参考或强复刻。
  - **产品交互层**：Agent 专属功能区、工作区切换、会话迁移、搜索、欢迎说明、功能入口等，允许参考，但必须映射到 Project_R 当前 PRD、阶段能力、后端权限与审计边界；未闭环功能只能明确标记为预留或后续接入。
  - **架构执行层**：Proma 的本地 Agent 执行链路、Electron IPC 业务编排、客户端 API Key 管理、模型配置暴露、MCP/Skills 本地执行、diff/文件改写链路等，默认禁止迁移，除非另行提出设计并获得 Gary 确认。
- 已获授权前提下，允许局部迁移或强复刻 Proma 前端的布局、组件观感与交互节奏，用于快速获得接近 Proma 的视觉体验；但不得迁移 Proma 的业务架构、Electron IPC 编排、客户端 API Key 管理、模型配置暴露、本地 Agent 执行链路或产品品牌形态。原则是：Proma shell first, Project_R core always。
- 允许在有明确收益时引入新的依赖或局部新架构，尤其是能更快解决功能质量、跨平台兼容或长期维护问题的成熟方案；新增依赖必须写入对应依赖声明文件，并说明用途。
- 已获 Gary 授权后，Agent 可以为项目运行必要的依赖安装命令；若出现网络超时、下载卡住、镜像不可用或连续失败，应及时中断并请 Gary 手动下载/安装，不要反复重试联网安装命令。
- 不要主动修改外部参考文件或历史参考目录（如存在），除非用户明确要求更新 PRD、开发流程、业务工作流清单等文档。

## 阶段执行规则

- 开发任务以 `Project_R 开发流程.md` 为准。
- 每个阶段先做最小竖切片，再补权限、错误、日志、跨平台与体验。
- 对开发流程中任一阶段执行开发时，如果某个任务已经实现且验证满足功能，必须同步把对应 checklist 从 `- [ ]` 改为 `- [x]`。
- 未验证、只完成设计、只完成后端但未接前端的任务保持未勾选，并在实现状态说明原因。
- 新增或修改业务 Skill 后，同步更新 `Project_R 业务工作流清单.md` 中对应状态与 SKILL.md 链接。
- 阶段约定若会影响后续代理工作，必须同步写入 `AGENTS.md`。

默认验证门槛：

- 后端改动：运行相关 `pytest`。
- 前端改动：运行 `bun run typecheck`；涉及打包、路由或构建配置时补跑 `bun run build`。
- 跨端链路：说明后端地址、测试账号、是否使用真实 LLM Key、是否需要 Gary 手工确认。

## 后端约定

后端采用 Python FastAPI + SQLite：

- `backend/main.py`：FastAPI 应用入口，注册路由并启动时初始化数据库。
- `backend/api/`：HTTP 路由层。
- `backend/core/`：LLM、RAG、意图识别、文件渲染、Skill 调度等核心逻辑。
- `backend/models/`：SQLAlchemy 数据模型。
- `backend/skills/builtin/`：官方内置业务 Skill。

已定义数据模型：

- `User`
- `ChatSession`
- `ChatMessage`
- `AuditLog`
- `KnowledgeReview`

LLM Provider 约定：

- 业务层只调用统一 LLM Provider 接口，不直接依赖某一家厂商 SDK。
- 默认 Provider 可为 Claude，但必须预留 OpenAI / ChatGPT、DeepSeek、MiMo 等厂商。
- `model_profile` 是用户可见的后端白名单模型配置档，不等于 API Key；多个 profile 可共享同一个 provider 的 Key 组，例如 DeepSeek Flash / Pro 共享 DeepSeek Key，MiMo V2.5 / V2.5-Pro 共享 MiMo Key。
- `/health/llm` 只返回已配置 provider/profile 的可用状态、模型名、描述与 Key 数量，严禁返回 Key 明文；员工前端只能展示已配置 profile。
- 思考模式由前端发送 `thinking` 布尔值，后端按 provider 生成实际 payload；DeepSeek 使用 `thinking.type` 与 `reasoning_effort`，MiMo 使用 `thinking.type`，不要在前端硬编码厂商私有参数。
- 每个 Provider 内部独立管理多个 API Key，并使用 Round-Robin 轮询。
- 单个 Key 遇到限流、网络错误或 5xx 时，自动尝试同 Provider 下一个 Key。
- 当前 Provider 所有 Key 均不可用时，向用户返回统一的 AI 服务不可用提示。
- 默认测试使用 mock LLM，不调用真实 Claude / OpenAI / DeepSeek API。

## 前端约定

- 使用 Electron + React + Vite + TypeScript + Jotai。
- Electron 主进程保持安全默认值：`contextIsolation: true`、`nodeIntegration: false`、最小化 `preload`；renderer 不直接访问 Node API。
- Electron 窗口使用软件内窗口控制：主工作台将最小化 / 最大化 / 关闭按钮融入标签栏右侧，登录、设置、欢迎等无标签页页面使用极简顶部拖拽兜底层；不得恢复系统主菜单栏或新增传统标题栏。
- 路由保留 `/login`、`/app`、`/settings`、`/onboarding`。
- 登录认证状态统一放在 `auth-atoms.ts`，包含 Token、当前用户、登录写入、登出清理。
- Phase 8 MVP 允许 `localStorage` 持久化 Token 与用户信息；后续安全加固再替换为 Electron 安全存储或系统凭据管理。
- API client 自动携带 JWT Token；遇到 401 必须触发本地登出或清理认证状态。
- `/app` 主界面必须受认证保护；未登录或 Token 失效时跳回 `/login`。
- `/app` 是真实聊天工作台，不显示开发期导航痕迹。
- `chat-atoms.ts` 集中管理会话列表、当前会话、消息列表、加载状态、发送状态与错误状态。
- 当前消息接口为 JSON 非流式；Phase 9 用前端打字机效果模拟逐字出现，真正 SSE 流式接口后续独立追加。
- 允许为 Markdown 渲染、文件生成、富文本处理等能力引入成熟依赖（如 `react-markdown`、`python-docx` 等），前提是收益明确、依赖可维护且已写入依赖声明；安装遇到网络问题时及时停止并交由 Gary 手动处理。
- 最小窗口 800×600 下，侧边栏、消息区、底部输入区不能重叠，关键按钮必须可用。
- 聊天工作台右上角允许保留置顶、并排模式、项目文件等 Proma 风格入口，但必须区分真实闭环与占位：置顶应做真实能力；并排模式已接入左右双对话槽位，点击某侧对话区后再选会话可把会话放入该侧；项目文件入口会切换右侧常驻 `WorkspaceFilePanel`，再次点击或点面板关闭按钮收起。提示词、Skills 与模型选择入口放在输入框底部工具区；提示词和 Skills 打开右侧常驻工具面板，选中后只在输入框上方显示状态标识，不改写用户输入文本；模型选择下拉向上展开，展示后端 `/health/llm` 返回的已配置 `model_profile`，发送消息时传 `model_profile` 与 `thinking`，不在前端暴露 API Key 或厂商私有参数。GBrain 引用来源应以可点击标签展示，并在右侧来源面板渲染 Markdown 片段；切换到其他会话时，来源面板必须自动关闭。
- 提示词系统按来源分为三类：Project_R 内置提示词（系统只读）、公司预设提示词（后端保存，管理员维护，普通用户调用）、用户自定义提示词（仅本机可用，Electron 主进程保存到 `app.getPath("userData")` 下，不进 Git、不上传后端）。提示词调用语义为“当前会话 system prompt”，不是插入输入框模板；每个会话独立选择提示词，新会话默认使用 Project_R 内置提示词；非默认提示词在输入框上方显示选择态 chip。
- `backend/prompt_presets/global-base-prompt.md` 是公司级 Global Base Prompt，属于后端强制注入的底层规则，不属于用户可切换提示词。system prompt 组合优先级为：全局底层规则 → 会话选择提示词 / Agent 模式提示 → 会话临时附件 → 知识库或项目资料 → 用户问题。
- Chat / Agent 产品边界的长期目标仍是“Chat 发现意图，Agent 承接执行”，但当前阶段临时改为**全部显式路由**：`core/intent.py` 默认只返回 `chat`；知识库问答必须使用 `/query ...`；业务 Skill 必须由用户在前端 Skill 面板手动选择并通过 `selected_skill` 启动；文件生成不再由普通自然语言自动触发。后续待 Skills 与 Agent 执行链路完整后，再恢复 Chat 自动发现意图、Agent 承接执行的模式，并同步恢复相关测试。
- 工作区在软件使用层面是项目资料容器；业务上每个项目工作区一一对应一个项目，通常以项目代号命名。代码内部继续使用 `workspace` 历史命名。公司项目资料位于 `backend/workspace_data/project/{品牌}/{项目代号}`，品牌固定为 `AURA`、`BFI`、`SPECWISE`、`SYNOVA`；用户默认工作区位于 `backend/workspace_data/user/{用户名}`，显示名为 `{用户名} 的私人空间`，可见置顶且不可删除、不可重命名、不可归档，且只对本人可见。第一版只有系统管理员可新建项目工作区；公司项目默认开放给所有用户，成员列表不代表全部访问者，只用于项目管理员、隐藏项目人员白名单和需要显式通知/治理的协作人；隐藏项目才按成员白名单和组别白名单限制搜索/进入。公司项目默认目录为 `01-合同与报价`、`02-图纸与技术资料`、`03-会议纪要`、`04-变更与签证`、`05-生产与发货`、`06-现场与客诉`、`99-未归档文件`；用户默认工作区默认目录为 `对话文件` 和 `固定文件`。Agent 模式默认显示当前工作区文件目录/上下文面板，供用户检查参考资料是否正确、是否遗漏；Chat 模式只提供轻量入口。当前已支持工作区多文件上传、回收区、恢复/永久删除、成员/管理员权限、审计日志、项目资料异步入库状态和项目 GBrain source 查询；项目对话只读取当前项目、未删除、已同步到当前项目 source 的资料。

## Phase 10-13 开发框架

- Phase 10 GBrain 知识库主线：正式知识库检索、项目资料检索、复盘总结和 Agent 知识调用默认走 GBrain source。旧 `backend/knowledge_base/wiki/` 与 `backend/vector_store/` 不得作为正式知识来源；已删除的旧 `core/wiki_router.py`、`core/rag_engine.py` 不得恢复为 fallback。
- GBrain `company-wiki` 第一阶段验收样本由 Gary 手动放入 `backend/workspace_data/global/company-wiki/raw/`；Agent 不要凭空生成测试文档或用合成资料冒充真实业务资料。建议最小样本为 3 个 Markdown / txt、2 个 PDF、1 份会议转写文本；PDF 样本用于验证结构化提炼质量，不作为纯文本抽取入库验收。
- Phase 10D/10E 工作区项目资料目录：工作区后端专用目录只允许在系统创建的工作区根目录内操作，不允许用户绑定任意本机目录。当前已重构为 `workspace_data/project/{品牌}/{项目代号}` 与 `workspace_data/user/{用户名}` 两类根路径，并已补项目 GBrain source、异步录入队列、复杂 PDF/图纸、图片/截图、MP4 自动/长视频分段转写、说话人/术语纠错、EML、EML 附件递归和引用定位 MVP；继续补文件预览、移动功能和更完整的项目质量回归。
- Phase 11 文件生成：先做 Word 竖切片，再扩展 PPT / Excel；生成文件必须校验用户访问权限并自动清理。
- Phase 12 业务 Skill：保留 Skill 底座，退役 U03 标签打印样板；后续以真实业务 Skill 做端到端验收，不先做泛化过度的平台。
- Phase 13 管理员后台：先做用户管理、知识刷新、知识审核、模板状态、审计日志 MVP，再扩展复杂报表和上传管理。

## Agent Skills

本项目基于 mattpocock/skills，通过 `skills-lock.json` 管理版本。

| 分类 | Skills |
|---|---|
| 工程 | `diagnose`、`grill-with-docs`、`improve-codebase-architecture`、`prototype`、`setup-matt-pocock-skills`、`tdd`、`to-issues`、`to-prd`、`triage`、`zoom-out` |
| 生产力 | `caveman`、`grill-me`、`handoff`、`write-a-skill` |

Issue tracker、triage labels、domain docs 见：

- `docs/agents/issue-tracker.md`
- `docs/agents/triage-labels.md`
- `docs/agents/domain.md`
