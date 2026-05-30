# GBrain 适配开发进度

状态：v0.7，2026-05-31  
用途：记录 Project_R 对 GBrain 的真实适配进度、完成边界、未闭环项和下一步开发顺序。

## 相关文档

| 文件 | 用途 |
|---|---|
| `docs/gbrain-feature-inventory.md` | GBrain 原生功能盘点矩阵：判断能力应直接沿用、adapter 包装、Skillify 补齐还是暂不接入。 |
| `docs/gbrain-ingest-workflow.md` | 原始资料进入 GBrain source 的导入、提炼、审核和索引流程。 |
| `docs/gbrain-agent-citation-fixer-runbook.md` | GBrain agent / citation-fixer 的 OAuth 绑定、worker 模式、DeepSeek gateway loop 和预检流程。 |
| `docs/adr/0003-gbrain-service-adapter.md` | 决定 Project_R 通过 GBrain HTTP/MCP service-account adapter 调用 GBrain。 |
| `docs/adr/0004-gbrain-company-wiki-source-path.md` | 决定 `derived/` 直接作为 `company-wiki` source repo。 |
| `docs/adr/0005-gbrain-derived-local-git.md` | 决定 `derived/` 使用本地 Git 做审计、对比和回滚。 |
| `docs/adr/0006-retire-legacy-rag.md` | 决定退役旧 Wiki Router / Chroma / vector_store 主路径。 |
| `docs/adr/0007-pdf-structured-extraction.md` | 决定 PDF 不再纯文本抽取直入库，必须结构化提炼后进入 GBrain。 |
| `docs/adr/0008-gbrain-upstream-maintenance-policy.md` | 决定不得无记录地修改 GBrain 上游源码，必要改动用 patch/fork 管理。 |
| `docs/adr/0009-pr-owned-extraction-to-gbrain-markdown.md` | 决定原始文件提炼归 Project_R Agent / Skills，GBrain 只接收 Project_R 产出的 Markdown 后做知识库内核处理。 |
| `docs/adr/0010-source-scoped-knowledge-ingest-review-policy.md` | 决定知识录入按来源空间分责：管理员公司知识免二次审核，私人空间不入公司库，项目工作区一键录入当前项目所有未入库文件，仅进入项目 source 并通知触发用户。 |
| `docs/adr/0011-automatic-extractor-routing-by-file-type.md` | 决定用户只触发录入，不选择 API Key；Project_R 后端按文件类型和复杂度自动选择 DeepSeek、MiMo、转写流程或 `pending_extractor_capability`。 |

## 总体判断

Project_R 目前不是“完整使用了 GBrain 全部功能”，而是已经完成了 GBrain 正式接入的第一条可用主链路：

```text
raw 真实样本
-> Project_R Agent / Skills 按格式提炼
-> 按 source scope 写入 company/project derived
-> GBrain company-wiki / project source
-> Ollama embedding / sync
-> /query 显式知识库查询
-> Project_R 聊天回答 + 来源展示
```

当前可以把旧 RAG 视为正式退役，但不能把 GBrain 完整适配视为完成。后续开发重点仍是 GBrain 完整适配，而不是跳过 GBrain 去做无关功能。

## 当前完成度

| 模块 | 状态 | 当前事实 |
|---|---|---|
| GBrain 运行方式 | 已完成 MVP | `core/gbrain.py` 已支持配置、health、source status、query、sync、doctor、启动/重启服务。正式调用走后端 service-account adapter，CLI 仅作初始化/诊断/应急。 |
| 全局 source | 已完成 MVP | 本机已注册 `company-wiki`，source path 指向 `backend/workspace_data/global/company-wiki/derived/`。 |
| 原始资料目录 | 已完成 MVP | `workspace_data/global/company-wiki/{raw,derived,manifests}` 已建立；`raw/` 由 Project_R 管，`derived/` 作为 GBrain source repo。 |
| derived 本地 Git | 已完成 MVP | `derived/` 已作为本地 Git repo 用于派生 Markdown 审计、对比和回滚。 |
| Markdown / txt 摄取 | 已完成第一版 | 可从 `raw/` 编译到 `derived/` 并进入 GBrain sync。 |
| DOCX 摄取 | 已完成第一版 | 可抽取正文/表格进入会议 Markdown；正式会议结构化提炼仍需加强。 |
| PDF 摄取 | 已完成 MVP | 已接入 MiMo 视觉辅助结构化提炼；公司 source 输出 `pending_review`，项目 source 一键录入时复杂 PDF/建筑图纸直接生成 source-scoped Markdown 后同步当前项目 source。仍未完成逐条条款回链、图表全量 OCR/视觉校验、章节级拆页策略。 |
| 音视频会议转写 | 已完成项目 MVP | MP3/MP4/MOV/MKV/WEBM 支持同名 transcript 侧车；项目 source 无 transcript 的 MP4 会优先抽取音频，按默认 300 秒分段调用 MiMo 自动转写，再用 DeepSeek 做说话人/术语纠错，最后生成 `meeting_structured_extract` Markdown。仍需加强置信度、绝对时间戳回链、人工抽检和公司 source 会议直入规则。 |
| Embedding | 已完成 MVP | 已切换到本地 Ollama + `mxbai-embed-large`，当前 GBrain sync 生成 1024 维向量，`chunks_unembedded=0`。 |
| `/query` 检索 | 已完成 MVP | Project_R 通过 GBrain `query` 显式传入 `source_id=company-wiki` 或当前项目 `project-*` source；中文问题通过受控英文扩展和分数修正改善标准类命中。 |
| 查询质量回归 | 已完成第一版并接入管理员入口 | 已建立 `backend/tests/fixtures/gbrain_query_regression_cases.json`、`backend/tests/test_gbrain_query_regression.py` 和真实服务脚本 `backend/scripts/gbrain_query_regression.py`。当前覆盖 AS 1288、AS 2047、VMU、0515 会议、书面化原则；管理员后台可触发 query 回归并查看通过数/失败原因。 |
| 聊天接入 | 已完成 MVP | 只有 `/query ...` 或等价知识库 Skill 调用 GBrain；普通 Chat 不自动查 GBrain，保留日常 chatbot 能力。 |
| 来源展示 | 已完成基础版 | 前端可展示 GBrain 来源标签，并在右侧来源面板渲染 Markdown 片段；项目 source 结果会尽量补 `derived_file`、`source_file`、`source_line`、`source_page` 和定位文本。 |
| 答案反馈纠错审核 | 已完成 MVP | 用户对带 GBrain 引用的回答打低分时，Project_R 会把反馈、原问题、原回答摘录和 GBrain 引用来源生成 `KnowledgeReview` 待审核项，并通过现有管理员知识审核与通知中心处理。 |
| 管理员状态 | 已完成 MVP | 管理员可查看 GBrain health、source、embedding、manifest、sync、doctor 摘要，并触发启动/重启、raw 导入、含 PDF 提炼、query 回归和显式 Think 回归。 |
| GBrain 维护任务 | 已完成第一版竖切片 | `core/gbrain.py` 已包装 GBrain MCP `run_onboard(mode=check)`、`list_jobs`、`submit_job`、`get_job`、`get_job_progress`、`cancel_job`、`retry_job`、`find_contradictions`；管理员后台新增 GBrain 维护页，可查看 jobs/contradictions/maintain check，提交 sync/embed/lint/backlinks 任务并取消/重试，操作写审计和通知中心。citation-fixer 已确认不是普通 job，而是 GBrain agent skill，后端已补 `submit_agent`/`submit_citation_fixer` 适配入口，前端管理员 GBrain 维护区已提供提交表单；agent readiness 已拆分为 `disabled/oauth_required/configured_unverified/ready`，并新增预检脚本。 |
| 知识审核 | 来源规则已落地 MVP | 管理员后台录入公司知识不需要额外审核；用户私人空间附件不进入公司库；项目工作区资料由项目用户点击一键录入后只进入该项目 source，不走公司知识审核。审核队列保留给答案反馈纠错、显式提升公司知识和异常情况。 |
| 旧 RAG 退役 | 已完成主路径 | `core/wiki_router.py`、`core/rag_engine.py`、旧 Chroma/vector_store 主路径和对应旧测试已退役，不作为 fallback。 |
| GBrain 上游维护 | 已建立规则 | 当前六处本地 GBrain 修改已记录为 `patches/gbrain/`；后续不得无记录修改上游源码。 |

## 未完成项

| 模块 | 状态 | 需要完成什么 |
|---|---|---|
| GBrain `think` | company-wiki 显式回答层已验收，默认未放行 | `GBrainAdapter.think()` 已接入 MCP `think`，支持 `/query --think ...` 与 `/think ...` 显式入口，能把 citations、gaps、warnings 归一化为前端来源面板可展示的来源项；`patches/gbrain/0003-think-source-scope-gather-and-takes.patch` 已补齐 `runGather()` 对 page/take/graph 检索流的 source scope 传递，并验证 PGLite takes keyword/vector scope。2026-05-30 已用 `company-wiki` source-scoped OAuth client 跑通真实 MCP `think` 调用，确认 token-bound source scope 生效；随后通过 `GBRAIN_THINK_MODEL=deepseek:deepseek-chat` 和 GBrain 进程内 `DEEPSEEK_API_KEY` 映射完成 DeepSeek 综合回答验证，`书面化原则是什么` 返回 `status=ok`、`modelUsed=deepseek:deepseek-chat`、`warnings=[]`、`citations>=1`。已新增真实服务 `think` 回归脚本固定该验收。默认仍关闭，原因是项目 source 的 think scope、更多问题回归和前端 gap/conflict 展示尚未闭环。 |
| 项目级 source | 已完成真实样本闭环 MVP | 已完成 adapter + 项目一键录入路径：项目 source id 稳定生成为 `project-{brand}-{workspace_id}`，路径绑定 `workspace_data/project/{品牌}/{项目代号}/derived/`，项目查询显式传 source scope，管理员状态返回项目 source 列表。2026-05-30 已用 `backend/workspace_data/project/BFI/GBrain验收项目-001/` 真实样本验收：synthetic 报价、VO08 变更 PDF、建筑图纸 PDF、MP4 会议录音和 EML 邮件均入项目 source；项目查询命中 synthetic 独特事实、邮件线程、会议行动项和图纸页，`company-wiki` 查不到项目 synthetic 事实。 |
| 项目资料真实索引 | 已完成真实样本闭环 MVP | `POST /workspaces/{id}/knowledge/ingest` 会先运行 extractor classifier，再编译项目文件、注册/同步项目 GBrain source，并按 sync 结果更新 `rag_status`。新增异步队列 `POST /workspaces/{id}/knowledge/ingest/async` 和 job 查询接口；前端一键录入改为排队 + 轮询。2026-05-31 真实验收 manifest 为 `total=11, compiled=11, pending_extractor_capability=0, pending_transcription=0, failed=0`。仍缺文件预览 UI 和更严格质量回归。 |
| 音视频会议 | 自动转写项目 MVP 已完成 | 已支持 MP3/MP4/MOV/MKV/WEBM + 同名 transcript 的会议结构化提炼；项目 source 无 transcript 的 MP4 会优先用本地 ffmpeg 抽取音轨，长媒体按分段转写，生成 `.auto.transcript.md`，再用 DeepSeek 进行说话人映射和术语纠错，随后进入会议结构化 Markdown。company-wiki 会议直入规则、置信度、绝对时间戳回链、人工抽检和真实音视频查询回归仍需加强。 |
| 图片 / 截图 | 已完成项目 MVP | 项目 source 路径已接入 `core/image_structured_extraction.py`，PNG/JPG/WEBP/BMP/GIF/TIFF 等图片会走 MiMo 视觉提炼，生成结构化 Markdown 后进入当前项目 `derived/`。仍需补更严格 OCR 质量回归、坐标/区域级引用定位和公司 source 图片规则。 |
| 邮件导出 | 已完成项目 MVP | `.eml` 可用标准库解析主题、发件人、收件人、日期、正文和附件名，再用 DeepSeek profile 提炼为中英文对齐的项目邮件线程 Markdown；LLM 不可用时有确定性 fallback。2026-05-31 已补附件递归：附件保存到 `<邮件名>.attachments/` 后重新进入 classifier，图片附件已能走 MiMo 提炼并入项目 source。邮箱批量导出、多邮件会话合并和公司知识提升仍未完成。 |
| GBrain maintain / doctor / jobs | 第一版竖切片已完成 | 管理员后台已接入 maintain check、jobs 列表、提交、取消、重试、通知和审计。仍缺真实后台 worker 长跑验收、定时维护策略、失败任务轮询通知、自动 remediation 费用/权限边界。 |
| citation-fixer / contradiction | citation-fixer 管理入口已接入，agent 只读 inline 执行已验收，真实改写未验收 | 管理员后台可读取 GBrain `find_contradictions` 最近探针结果；带 GBrain 引用回答的低分反馈会生成知识纠错审核项。已确认 citation-fixer 是 `skills/citation-fixer/SKILL.md`，执行路径应走 GBrain MCP `submit_agent`，而不是 `submit_job`。当前已有 `POST /admin/knowledge/gbrain/citation-fixer` 和管理员 UI 表单；`backend/scripts/gbrain_agent_preflight.py` 可检查非敏感 readiness；`patches/gbrain/0004-agent-bound-oauth-client-registration.patch` 已补齐 GBrain CLI/provider 的 agent-bound OAuth client 注册入口。2026-05-30 已新增安全注册脚本、gateway loop 配置脚本、submit_agent 绑定烟测脚本和 PGLite inline 执行烟测脚本；本机已注册真实 agent-bound OAuth client，启用 `agent.use_gateway_loop=true`，通过 Project_R adapter -> GBrain MCP `submit_agent` 创建后取消一条 citation-fixer subagent job，并通过 `jobs submit subagent --follow` 完成 `company-wiki` source 内 `search/get_page` 只读执行，预检显示 inline execution 已验证。仍需验收真实 citation-fixer 改写型 subagent 和长期 worker/任务完成策略。 |
| graph / timeline | 未接入业务流程 | 需要用于项目复盘、会议/邮件追踪、项目事件沉淀和公司知识演进。 |
| schema pack | 未定制 | 当前使用默认 `gbrain-base-v2`；后续需要评估是否为项目资料、会议、标准、合同等设计 Project_R schema pack。 |
| Project_R extractor classifier / skills | 项目主链路 MVP 已完成，仍需 Skill 化 | 已实现 `core/extractor_classifier.py`，普通用户不选择 API Key；Project_R 后端先按 `source_scope`、`file_kind`、`extraction_complexity` 自动选择 `extractor_profile/model_profile`。文字/Markdown/DOCX/普通 PDF、复杂 PDF/图纸、图片/截图、MP4 自动/长视频分段转写、说话人/术语纠错、EML 邮件线程和 EML 附件递归已能进入项目 source。批量邮件线程合并、置信度、绝对时间戳回链、区域级图片引用和可重复 Project_R Agent / Skills 封装仍未完成。GBrain Skillify 只保留为后 Markdown 阶段或设计参考。 |
| 查询质量回归扩展 | 已有第一版，仍需扩展 | 当前回归集覆盖第一批真实样本；后续需要加入更多公司规则、会议行动项、PDF 条款级引用、项目 source 样本和升级前后对比报告。 |
| Reranker | 未评估 | 当前靠 GBrain hybrid/vector + Project_R 分数修正；是否追加本地 reranker 需要基于回归集判断。 |

## 下一步开发顺序

当前重点仍是 GBrain 完整适配。推荐顺序：

1. 扩展 GBrain 查询质量回归集：第一版已建立，后续继续加入更多真实问题、期望 source、期望引用片段和升级前后对比，防止 GBrain、Ollama、chunk 或 PDF 提炼变化导致检索倒退。
2. 扩展项目 extractor 能力：建筑图纸/复杂 PDF 的 MiMo 视觉提炼、EML 邮件线程解析、EML 附件递归、图片/截图提炼、MP4 自动分段转写和说话人/术语纠错已完成项目 MVP；下一步补人工抽检、质量回归集、区域级引用定位和文件预览 UI。
3. 完成 GBrain `think` 回答层放行：guarded adapter、上游 gather/takes source-scope patch、`company-wiki` source-scoped OAuth + MCP 服务调用、DeepSeek 综合回答、citations 和第一条 `think` 回归已验证；下一步补齐项目 source 的 OAuth/scope 验证、扩展 `think` 质量回归、gap/conflict 前端展示后，才可把 `think` 从显式试用入口提升为 `/query` 可选或默认回答层。
4. 做音视频会议提炼：MP4 自动转写 + 会议结构化项目 MVP 已完成，并已补长视频分段、说话人映射和术语纠错；下一步接入置信度、绝对时间戳回链质量控制、人工抽检、音视频查询回归和公司知识沉淀规则。
5. 完善 GBrain 维护能力：第一版已接入 maintain check、jobs、contradiction 展示、取消/重试、通知和审计，且低分 GBrain 答案反馈已能进入知识纠错审核；citation-fixer 已按 GBrain agent skill 路径补后端提交入口、管理员表单和预检脚本；GBrain 本地 patch 已补齐带 `bound_tools/source/slug_prefix/budget` 的 agent OAuth client 注册方式。2026-05-30 已完成真实 client 注册、DeepSeek gateway loop 配置、submit_agent 绑定冒烟和 PGLite 只读 inline subagent 执行烟测。下一步是用审核保护的测试页跑真实 citation-fixer 改写型 subagent，或切到 Postgres worker 后做长跑验收。
6. 固化 Project_R extractor skills：统一分类器和项目主链路已实现；下一步把项目复盘、资料提炼、PDF/复杂 PDF、音频/视频、会议沉淀、图片/截图和邮件整理封装成可重跑、可配置、可观测的 Project_R Agent / Skills；GBrain 继续负责 Markdown 入库后的 query/think/citation/maintain/graph 等流程。

## 2026-05-30 查询质量回归集

- 新增回归用例：`backend/tests/fixtures/gbrain_query_regression_cases.json`。
- 新增离线单元测试：`backend/tests/test_gbrain_query_regression.py`，使用 fake GBrain adapter 验证 Project_R 的查询扩展、来源归一化和排序逻辑。
- 新增真实服务脚本：`backend/scripts/gbrain_query_regression.py`，会读取本机 `.env`，检查 GBrain HTTP service、`company-wiki` source、Ollama embedding readiness，并对真实 GBrain `/query` 跑回归用例。
- 新增管理员回归入口：`POST /admin/knowledge/regression` 默认运行 query 回归，`include_think=true` 时额外运行 Think 回归；前端管理员设置页提供“查询回归”和“Think 回归”按钮，并展示通过数、失败用例和 preflight 错误。
- 当前用例覆盖：AS 1288 安全玻璃、AS 2047 防水/水密、热浸测试、VMU 客户参观接待、0515 会议行动项、书面化原则。
- 本次真实脚本曾发现 `书面化原则是什么` 被错误排到 VMU/会议来源之后；已在 `core/knowledge_sources.py` 增加规则类 query expansion、中文规则/流程类标题化查询变体、rules 来源加权、精确标题命中加权和会议噪声惩罚。PGLite 重建后再次出现该排序退化，已通过标题化查询变体让 `书面化原则` 稳定首位命中。
- 验证结果：`venv\Scripts\python.exe -m pytest tests\test_gbrain_query_regression.py tests\test_gbrain_config.py tests\test_gbrain_ingest.py tests\test_rag_api.py -q` 通过；`venv\Scripts\python.exe scripts\gbrain_query_regression.py` 真实服务回归通过。

## 2026-05-30 项目级 Source Adapter

- 新增项目 source 映射规则：每个 Project_R 项目工作区使用稳定 source id `project-{brand}-{workspace_id}`，例如 `project-bfi-7`；不使用项目名称或 slug 作为主键，避免项目改名导致历史引用漂移。
- 项目 source path 绑定到该项目工作区下的 `derived/`：`backend/workspace_data/project/{品牌}/{项目代号}/derived/`。项目根目录和 `manifests/` 仍由 Project_R 管理。
- GBrain 注册命令使用 `--no-federated`，项目 source 默认不参与跨 source 联合检索；只有用户具备该项目权限且查询当前项目时，Project_R 才显式传入该项目 `source_id`。
- `core/gbrain.py` 已提供 `project_source_id_for_workspace`、项目 source registration plan/status、项目 source ensure/sync adapter。
- `core/knowledge_sources.py` 已支持项目级 GBrain query scope：项目资料查询会调用 `GBrainAdapter.query(..., source_id=project-bfi-*)`，避免跨项目泄露；未注册或服务未配置时仍保留现有轻量项目文本召回作为过渡。
- `/admin/knowledge/status` 已返回 `project_sources`，管理员可以看到每个项目 source 的 source id、path、注册状态和路径匹配状态。
- `POST /workspaces/{workspace_id}/knowledge/ingest` 已接入项目 GBrain 编译、目录准备、source 注册与同步；`/knowledge/refresh` 仅保留为兼容别名。`POST /workspaces/{workspace_id}/knowledge/ingest/async` 已提供后台 job 队列，前端一键录入默认走异步排队并轮询结果。2026-05-30 已用 `GBrain验收项目-001` 完成真实端到端验收。
- 新增 `backend/tests/test_gbrain_project_sources.py`，覆盖 source id 稳定性、registration plan、source status path match、项目查询强制 source scope。
- 验证结果：`venv\Scripts\python.exe -m pytest tests\test_gbrain_project_sources.py tests\test_gbrain_config.py tests\test_rag_api.py -q` 通过。

## 2026-05-30 项目资料编译到 Project Source

- 新增 `backend/core/gbrain_project_ingest.py`：扫描 Project_R 项目工作区根目录，排除 `derived/`、`manifests/`、`.trash/`、`.git/` 和 PDF 同名图片侧车目录。
- 项目目录到 GBrain derived 分类的第一版映射：`01-合同与报价 -> contracts`、`02-图纸与技术资料 -> technical`、`03-会议纪要 -> meetings`、`04-变更与签证 -> changes`、`05-生产与发货 -> production`、`06-现场与客诉 -> site`、`99-未归档文件 -> unfiled`。
- Markdown/txt 会保留或补充 frontmatter，写入项目来源、workspace id、品牌、项目代号、source hash 和 ingest 时间。
- DOCX 会抽取正文/表格进入项目 Markdown；会议目录下的 DOCX 标记为 `meeting_transcript`，其他目录标记为 `project_docx_text_extracted`。
- PDF 录入由 classifier 先判定：普通 PDF 走可选文本抽取到项目 `derived/`，复杂 PDF/建筑图纸默认启用 MiMo 结构化提炼并写入项目正式 `derived/`，不再走项目 pending review。
- 2026-05-31 自动路由规则已落地并扩展：新增 `core/extractor_classifier.py`，项目文件录入前输出 `source_scope`、`file_kind`、`extraction_complexity`、`extractor_profile` 和 `classifier_reason`。普通用户不选择 API Key；后端自动把 Markdown/TXT/DOCX/普通 PDF 路由到文字路线，把复杂 PDF/图纸路由到 MiMo 结构化路线，把音视频路由到转写流程，把 EML 路由到邮件线程提炼并递归处理附件，把图片/截图路由到 MiMo 视觉提炼。
- 工作区一键录入接口已接入项目编译结果：`POST /workspaces/{workspace_id}/knowledge/ingest` 先编译项目文件并写 `manifests/project-source-ingest-manifest.json`，再确保 GBrain 项目 source 注册并同步；正式 compiled 文件只有在 sync 成功后才标记 `rag_status=indexed`。上传文件和会话附件保存不再误标 `indexed`。异步队列由 `WorkspaceIngestJob` 记录 `queued/running/succeeded/failed`、结果 JSON 和失败原因。
- 项目 pending review 不再作为默认路径；项目文件由用户在项目文件面板点击“一键录入项目知识库”后，批量录入当前项目所有知识目标范围内且尚未入库的文件；已具备 extractor 的文件直接写入当前项目 `derived/` 并同步对应 project source，不进入公司库、不创建公司知识审核项；暂未具备 extractor 的文件保留为 `pending_extractor_capability` 或明确失败状态；完成或失败后通知点击录入的用户。
- 前端项目文件面板已改为“一键录入项目知识库”，显示待录入数量、排队/执行中状态、完成/失败提示，并展示 `已入库 / 未入库 / 待能力补齐 / 待转写 / 失败 / 暂不入库` 等文件状态。
- 新增和改写测试覆盖项目 Markdown/txt、DOCX、普通 PDF 路由、复杂 PDF/图纸 MiMo 提炼、图片/截图 MiMo 提炼、媒体自动转写、长视频抽音频后越过原视频体积限制、说话人/术语纠错元数据、EML 邮件提炼、EML 附件递归、项目 source sync、项目不创建管理员审核项、异步 job 和通知触发用户。
- 2026-05-31 已完成真实项目样本增量验收：将 `backend/workspace_data/project/BFI/GBrain验收项目-001/` 注册为 Workspace，并补入明确标记为 synthetic/test fixture 的 `01-合同与报价/测试报价说明.md`，用于替代未提供的真实合同/报价样本。新增 `99-未归档文件/审批流程规则.png` 和长视频 `260512 Trn [项目组与设计组人员分工调整规划] Shak -video.mp4` 后重新执行一键录入，manifest 为 `total=11, compiled=11, pending_extractor_capability=0, pending_transcription=0, skipped=0, failed=0`。
- 真实样本分类结果：synthetic 报价 Markdown 入 `contracts/测试报价说明.md`；建筑图纸 PDF `A---2204-GENERAL-ARRANGEMENT-LEVEL-06---TYPICAL-06---10-Rev.4.pdf` 走 `vision_required` / `mimo_vision` 并入 `technical/`；普通项目变更 PDF 入 `changes/`；短 MP4 会议录音自动生成 `.auto.transcript.md` 后入 `meetings/`；长视频抽取音频后分 11 段转写，并通过 DeepSeek 生成 `Speaker Map / 说话人映射`、`Corrected Transcript / 术语纠错后转写` 和术语纠错记录；截图 `审批流程规则.png` 走 MiMo 视觉提炼并入 `unfiled/审批流程规则.md`；EML 邮件入 `unfiled/RE-   Lucerna - Apt. Type 5 Window.md`，并抽出 4 个图片附件到 `99-未归档文件/RE-   Lucerna - Apt. Type 5 Window.attachments/` 后递归编译为 4 个 Markdown。
- 查询隔离与定位验证：项目 source `/query` 能命中 synthetic 独特事实 `PR_GBRAIN_PROJECT_SOURCE_SYNTHETIC_FACT_20260530` 和 `SYN-QUOTE-GRAIN-001`，也能命中 Lucerna 邮件、20260529 会议行动项和 GENERAL ARRANGEMENT 图纸页；每条项目来源尽量返回 `derived_file`、`source_file`、`source_line` 和 `source_page`，并在来源内容末尾附加定位块。`company-wiki` 同 synthetic 问题不包含该项目事实。
- 通知验证：触发用户收到 `项目知识库录入完成`，内容为 `GBrain验收项目-001：已入库 5 个文件，待能力补齐 0 个，待转写 0 个，失败 0 个。`
- 验证结果：`venv\Scripts\python.exe -m pytest tests\test_media_transcription.py tests\test_gbrain_project_ingest.py tests\test_gbrain_project_sources.py tests\test_workspace_files.py tests\test_extractor_classifier.py -q` 通过，34 passed；`venv\Scripts\python.exe -m pytest -q` 后端全量通过，191 passed、6 subtests passed；前端 `bun run typecheck` 通过。

未闭环：该验收说明项目 source 一键录入、复杂 PDF/图纸视觉提炼、图片/截图视觉提炼、MP4 自动转写、长视频分段、说话人/术语纠错、EML 邮件线程提炼、EML 附件递归、项目内引用定位和异步队列均完成 MVP；但模型提炼质量仍需人工抽检和回归集扩展。尤其长视频当前分段时间戳仍以段内时间为主，尚未做全局绝对时间轴合并；说话人识别依赖模型推断，不等同于专业 diarization；图片提炼仍需补区域级引用定位。文件预览 UI 尚未完成。

## 2026-05-30 GBrain Think Guarded Adapter

- 调研结论：GBrain HTTP/MCP 的 `think` operation 通过 OAuth/AuthInfo 取得 `sourceId` 或 `allowedSources`，legacy bearer token 在 HTTP path 默认落到 `default` source；source-scoped client 应通过 `gbrain auth register-client ... --source company-wiki --federated-read company-wiki` 这类方式创建。
- 发现风险：上游 `runThink()` 虽然接收 `sourceId/allowedSources`，但 `runGather()` 未把这些参数传入 page/take 检索流；同时 `searchTakes()` / `searchTakesVector()` SQL 只过滤 holder，未过滤 `pages.source_id`。这会让多项目场景下的 `think` 存在跨 source evidence 泄露风险。
- 上游 patch：已修改 `reference/gbrain-master` 并记录为 `patches/gbrain/0003-think-source-scope-gather-and-takes.patch`。变更将 `sourceId/allowedSources` 从 `runThink()` 传入 `runGather()`，并继续传给 `hybridSearch`、`searchTakes`、`searchTakesVector`、`traversePaths`；PGLite/Postgres 的 takes keyword/vector SQL 均增加 `sourceId/sourceIds` 过滤。
- 新增配置：`GBRAIN_THINK_ENABLED`、`GBRAIN_THINK_SOURCE_SCOPE_VERIFIED`、`GBRAIN_THINK_ALLOWED_SOURCES`、`GBRAIN_THINK_OAUTH_CLIENT_ID`、`GBRAIN_THINK_OAUTH_CLIENT_SECRET`、`GBRAIN_THINK_MODEL`、`GBRAIN_THINK_ROUNDS`、`GBRAIN_THINK_TIMEOUT_SECONDS` 等。未显式开启或未确认 source scope 时，adapter 返回可审计的禁用/未验证状态；普通 GBrain status/query 仍使用短超时，`think` 单独使用较长超时。本机使用 `GBRAIN_THINK_MODEL=deepseek:deepseek-chat`，`scripts/start-gbrain.ps1` 会把 Project_R 的 `DEEPSEEK_API_KEYS` 第一枚可用 key 映射为 GBrain 进程需要的 `DEEPSEEK_API_KEY`，不打印明文。
- 新增后端能力：`core/gbrain.py` 增加 OAuth client_credentials token 获取和 `think()` MCP 调用；`core/knowledge_sources.py` 增加 think 结果归一化，把 citations、gaps、conflicts、warnings 映射为聊天来源面板可展示的来源项；`api/chat.py` 增加 `/query --think ...` 与 `/think ...` 显式路由，普通 Chat 仍不自动查 GBrain。
- 新增 `think` 回归：`backend/tests/fixtures/gbrain_think_regression_cases.json` 固定 `书面化原则是什么` 的 expected source/model/citation/answer terms；`backend/scripts/gbrain_think_regression.py` 会检查 GBrain service、source scope、OAuth 配置、DeepSeek model、warnings、citations 和答案关键词；`backend/tests/test_gbrain_think_regression.py` 离线验证回归判定逻辑；管理员回归入口在 `include_think=true` 时调用同类校验逻辑。
- 验证结果：`python -m py_compile backend\core\gbrain.py` 通过；`venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_chat_phase6.py tests\test_gbrain_project_sources.py tests\test_gbrain_query_regression.py -q` 通过，结果为 61 passed；`venv\Scripts\python.exe -m pytest tests\test_admin_phase13.py tests\test_workspace_files.py tests\test_gbrain_project_ingest.py -q` 通过，结果为 25 passed；`venv\Scripts\python.exe -m pytest -q` 后端全量通过，结果为 144 passed；`venv\Scripts\python.exe scripts\gbrain_query_regression.py` 真实服务回归通过。GBrain 上游验证：`bun run typecheck` 通过；`bun test test/takes-engine.test.ts test/think-pipeline.serial.test.ts` 通过，结果为 50 passed。
- 真实 MCP `think` 验收结果：已创建并配置 `company-wiki` source-scoped OAuth client，`GBrainAdapter.think("书面化原则是什么", source_id="company-wiki")` 返回 `status=ok`、`method=mcp`、`http_status=200`、`source_scope.verified=true`、`scope_is_token_bound=true`，证明 Project_R -> OAuth token -> MCP `think` -> GBrain source scope 调用链已跑通。配置 DeepSeek 后，同一问题返回 `modelUsed=deepseek:deepseek-chat`、`warnings=[]`、`gaps=0`、`citations>=1`，答案能引用 `rules/书面化原则`。
- 未闭环：当前只验证了 `company-wiki` 的显式 `/query --think` / `/think` 路径和第一条真实 `think` 回归，尚未完成项目 source 的 source-scoped OAuth/think 验证、多业务问题 `think` 回归、前端 gap/conflict 展示和默认回答层策略。因此不能宣称 `/query` 默认回答层完成。

## 2026-05-30 音视频会议转写 MVP

- 新增 `backend/core/meeting_structured_extraction.py`：将已有会议转写文本提炼为会议结构化 Markdown，固定 `language_policy=bilingual_zh_en_aligned`，并输出会议主题、关键决策候选、行动项候选、风险/待确认事项、可沉淀公司知识候选、时间戳摘录和原文转写。
- 支持同名 transcript 侧车文件：`<媒体名>.transcript.md/.txt/.vtt/.srt/.json`、`<媒体名>.zh-CN.transcript.*`、`<媒体名>.zh.transcript.*`、`<媒体名>.en.transcript.*`、直接 `.vtt/.srt`，以及同名目录 `transcript.md/txt/vtt/srt`。JSON 支持 `text` 或 `segments`。
- `company-wiki` raw ingest 已支持 MP3/MP4/MOV/MKV/WEBM：有 transcript 时写入 `derived/.pending_review/meetings/<媒体名>.md`，manifest 标记 `review_status=pending_review`、`transcription_status=transcript_sidecar_provided`、`approved_target_file=meetings/<媒体名>.md`；无 transcript 时跳过并标记 `pending_meeting_transcription` / `pending_transcription`。
- 项目 source ingest 已支持相同规则：项目会议目录下的媒体 + transcript 会直接进入该项目正式 `derived/meetings/` 并同步对应 project source，不走管理员公司知识审核。
- 项目 source 无 transcript 的 MP4 会先用本地 ffmpeg 抽取音频，再调用 MiMo 音频理解生成 `.auto.transcript.md`，随后复用会议结构化提炼流程；如果音频抽取失败，才尝试 MiMo 视频输入。
- transcript 侧车文件本身不会被重复当作 raw 文件扫描；只有没有对应媒体文件的独立文本转写，才按普通 Markdown/txt 或 DOCX 路径处理。
- 2026-05-31 补充：项目 MP4 自动转写已支持长媒体默认 300 秒分段，并用 DeepSeek 进行说话人映射和术语纠错；manifest 会记录 `transcription_segment_count`、`transcript_refinement_status`、refinement provider/model 和术语表。未闭环：低置信标记、绝对时间戳回链、专业 diarization、真实会议音视频查询回归和公司 source 会议直入规则收紧。
- 验证结果：`python -m py_compile backend\core\meeting_structured_extraction.py backend\core\gbrain_ingest.py backend\core\gbrain_project_ingest.py` 通过；`venv\Scripts\python.exe -m pytest tests\test_gbrain_ingest.py tests\test_gbrain_project_ingest.py -q` 通过，12 passed；`venv\Scripts\python.exe -m pytest tests\test_admin_phase13.py tests\test_workspace_files.py tests\test_gbrain_ingest.py tests\test_gbrain_project_ingest.py -q` 通过，34 passed；`venv\Scripts\python.exe -m pytest -q` 后端全量通过，151 passed、6 subtests passed；`venv\Scripts\python.exe scripts\gbrain_query_regression.py` 真实 GBrain `/query` 回归通过，6/6 passed。

## 2026-05-30 GBrain 维护任务 MVP

- 新增后端 adapter：`GBrainAdapter.maintenance_status()` 聚合 `run_doctor`、`get_status_snapshot`、`list_jobs`、`find_contradictions` 和 `run_onboard(mode=check)`；`submit_job` 本地白名单只允许 GBrain 声明的维护 job：`sync`、`embed`、`lint`、`import`、`extract`、`backlinks`、`autopilot-cycle`，明确不开放 `shell`。
- 新增管理员 API：`GET /admin/knowledge/gbrain/maintenance`、`POST /admin/knowledge/gbrain/maintenance/check`、`GET/POST /admin/knowledge/gbrain/jobs`、`GET /admin/knowledge/gbrain/jobs/{id}`、`POST /admin/knowledge/gbrain/jobs/{id}/cancel`、`POST /admin/knowledge/gbrain/jobs/{id}/retry`、`GET /admin/knowledge/gbrain/contradictions`。
- 管理员后台新增“GBrain 维护”页：显示 doctor 分数、jobs 接口状态、最近任务、contradiction 数、maintain check 状态；可提交 `sync/embed/lint/backlinks` 任务，并对已有任务取消/重试。
- 通知中心接入 GBrain 维护事件：维护检查、job 提交、取消、重试会给管理员创建 `open_settings` 通知，payload 指向管理员 GBrain 维护页；所有变更写 `AuditLog`。
- citation-fixer 调研和适配：上游 `skills/citation-fixer/SKILL.md` 声明 tools 为 `search/get_page/put_page/list_pages`，并通过 resolver 触发；它不是 `submit_job` 的 job name。Project_R 已新增 `GBrainAdapter.submit_agent()` 和 `GBrainAdapter.submit_citation_fixer()`，管理员 API 为 `POST /admin/knowledge/gbrain/citation-fixer`，提交后仍走 GBrain `subagent` job，并写审计/通知。前端 `SettingsModal` 与独立 `SettingsPage` 的管理员 GBrain 维护区已补 citation-fixer 提交表单，可填写 page slug、review id、slug 前缀、turns 和备注。
- citation-fixer 配置边界：该入口默认关闭，需要 `GBRAIN_AGENT_ENABLED=true`、`GBRAIN_AGENT_OAUTH_CLIENT_ID`、`GBRAIN_AGENT_OAUTH_CLIENT_SECRET`，且 GBrain 侧 OAuth client 必须带 `agent` scope、绑定 `search/get_page/put_page/list_pages` 工具、绑定 source/slug 前缀和预算。未配置时返回 `disabled/oauth_required`；已配置 OAuth 但未真实验收时返回 `configured_unverified`，只有 `GBRAIN_AGENT_EXECUTION_VERIFIED=true` 后才显示 `ready`。`GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED=true` 只表示 GBrain 接受了 `submit_agent` 绑定，不等同于执行完成。`maintenance_status` 已返回非敏感 agent readiness，前端显示 `agent OAuth` 状态但不暴露 client secret。
- agent 预检：新增 `backend/scripts/gbrain_agent_preflight.py` 和 `docs/gbrain-agent-citation-fixer-runbook.md`，记录上游 `submit_agent` 对绑定型 OAuth client 的要求、注册命令、PGLite 不能跑 persistent worker、DeepSeek 需要 `agent.use_gateway_loop=true` 的边界。2026-05-30 新增 `backend/scripts/gbrain_register_agent_client.py`、`backend/scripts/gbrain_enable_agent_gateway_loop.py`、`backend/scripts/gbrain_agent_submit_smoke.py`、`backend/scripts/gbrain_agent_inline_execution_smoke.py`，分别用于脱敏注册、写入 gateway loop、绑定冒烟和 PGLite inline 执行烟测。
- 上游 patch：`patches/gbrain/0004-agent-bound-oauth-client-registration.patch` 已修改 `reference/gbrain-master` 的 `registerClientManual()` 与 `auth register-client`，支持写入 `bound_tools`、`bound_source_id`、`bound_slug_prefixes`、`bound_max_concurrent` 和 `budget_usd_per_day`，并补充 CLI parser 与 OAuth provider 测试。`patches/gbrain/0005-subagent-tool-source-scope.patch` 修复 subagent brain tools 默认落到 `default` source 的风险，使工具调用继承 `submit_agent` 的 OAuth-bound source。`patches/gbrain/0006-chat-tool-json-schema-wrapper.patch` 修复 AI SDK v6 tool schema/message 兼容问题，使 `deepseek:deepseek-chat` gateway loop 能正常执行工具调用。
- 本机 agent 验收更新：已注册真实 agent-bound OAuth client，secret 只写入 `backend/.env`；已执行 GBrain `config set agent.use_gateway_loop true --force` 并写入 `GBRAIN_AGENT_GATEWAY_LOOP_VERIFIED=true`；已通过 `scripts/gbrain_agent_submit_smoke.py` 调 Project_R adapter -> GBrain MCP `submit_agent`，创建 `job_id=101` 后立即取消；已通过 `scripts/gbrain_agent_inline_execution_smoke.py` 调 GBrain 原生 `jobs submit subagent --follow`，在 `source_id=company-wiki`、只读工具 `search/get_page`、`mutation=disabled` 下完成 inline 执行，写入 `GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=true`。预检显示 `configured_unverified`、inline execution verified、`execution_verified=false`。
- 未闭环：当前只是把 GBrain 原生维护能力产品化到 PR 的第一条竖切片，并验证了只读 inline subagent；尚未跑真实长期 worker、未做任务完成轮询通知、未验收真实 citation-fixer 改写型 subagent、未把 contradiction probe 的生成任务纳入定时维护，也没有开放自动 remediation。
- 验证结果：`python -m py_compile backend\core\gbrain.py backend\api\rag.py backend\core\notification_service.py` 通过；`venv\Scripts\python.exe -m pytest tests\test_rag_api.py tests\test_notifications_phase18.py -q` 通过，14 passed；`venv\Scripts\python.exe -m pytest -q` 后端全量通过，155 passed、6 subtests passed；`bun run typecheck` 通过；加载 `.env` 后直接调用 `GBrainAdapter().maintenance_status()` 返回 `doctor/jobs/contradictions/onboard_check=ok`；`venv\Scripts\python.exe scripts\gbrain_query_regression.py` 真实 GBrain `/query` 回归通过，6/6 passed。后续补充：`python -m py_compile backend\core\gbrain.py backend\api\rag.py` 通过；`venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_rag_api.py -q` 通过，33 passed；`venv\Scripts\python.exe -m pytest -q` 后端全量通过，160 passed、6 subtests passed；`venv\Scripts\python.exe scripts\gbrain_query_regression.py` 真实 GBrain `/query` 回归通过，6/6 passed；前端 `bun run typecheck` 通过。本轮 agent 补充验证：GBrain `bun test test\ai\gateway-tool-loop.test.ts test\brain-allowlist.serial.test.ts test\submit-agent.test.ts` 通过，45 passed；GBrain `bun run typecheck` 通过；后端 `venv\Scripts\python.exe -m pytest tests\test_gbrain_config.py tests\test_gbrain_agent_inline_execution_smoke.py tests\test_gbrain_agent_submit_smoke.py tests\test_gbrain_register_agent_client.py tests\test_gbrain_enable_agent_gateway_loop.py tests\test_gbrain_query_regression.py tests\test_gbrain_think_regression.py -q` 通过，47 passed、6 subtests passed；`scripts\gbrain_query_regression.py`、`scripts\gbrain_think_regression.py`、`scripts\gbrain_agent_submit_smoke.py` 和 `scripts\gbrain_agent_inline_execution_smoke.py` 均通过。

## 2026-05-30 答案反馈到知识纠错审核 MVP

- `POST /chat/sessions/{session_id}/messages/{message_id}/feedback` 已扩展：普通评分仍写入结构化 JSON；当评分 `<=2` 且回答包含 GBrain 引用来源时，会自动生成 `KnowledgeReview`，source 使用 `gbrain_answer_correction:message:{message_id}`。
- 纠错审核内容会带上反馈 id、评分、用户、会话、项目/公司范围、原问题、原回答摘录、GBrain 引用来源和管理员处理建议，用于判断是事实错误、来源过期、引用缺失、资料冲突，还是回答组织问题。
- 该流程复用现有管理员知识审核与通知中心：创建或更新 pending review 后调用 `notify_knowledge_review_pending`，管理员可在知识审核入口通过、驳回或修改后通过。审核通过仍走现有 `derived/reviews/知识审核沉淀.md` 和 GBrain sync 路径。
- 当前边界：这不是 citation-fixer 自动修复；系统不会直接改引用或覆盖事实。citation-fixer、contradiction 修正和 Skillify 后的知识纠错 skill 仍是后续项。
- 验证结果：`python -m py_compile backend\api\chat.py` 通过；`venv\Scripts\python.exe -m pytest tests\test_chat_phase6.py -q` 通过，36 passed；`venv\Scripts\python.exe -m pytest tests\test_chat_phase6.py tests\test_admin_phase13.py tests\test_notifications_phase18.py -q` 通过，50 passed；`venv\Scripts\python.exe -m pytest -q` 后端全量通过，157 passed、6 subtests passed；`bun run typecheck` 通过；`venv\Scripts\python.exe scripts\gbrain_query_regression.py` 真实 GBrain `/query` 回归通过，6/6 passed。

## 完整适配完成标准

只有同时满足以下条件，才能说 Project_R 已完整适配 GBrain 框架：

1. 公司全局 source 与至少一个项目 source 都能完成闭环：管理员公司知识 `raw -> derived -> sync -> query/think -> citation`；项目知识“项目文件面板一键录入 -> project derived -> sync -> 项目内 query/think -> citation -> 通知触发用户”。
2. `/query` 不只是返回 chunk，而是能够稳定使用 GBrain query/think、引用、gap/conflict 信息。
3. PDF、复杂 PDF、会议转写、音视频、图片/截图、邮件至少都有明确的 Project_R extractor 流程、失败状态、pending capability 状态和按 source scope 入库策略。
4. 管理员后台能运行和查看 GBrain health、doctor、maintain、jobs、sync、review、失败重试和质量回归结果。
5. 用户反馈错误答案后，系统能进入知识纠错流程，而不是只让用户重新问。
6. GBrain 上游升级有 patch 审计和查询回归验证，不能靠手工记忆维护。
