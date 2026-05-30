# GBrain 功能盘点矩阵

状态：v0.1，Project_R 接入 GBrain 前置盘点。  
来源：本地 `reference/gbrain-master`，`package.json` 版本 `0.41.26.0`，以及 GBrain README、docs、skills、`src/core/operations.ts` 等源码。  
目的：后续 Project_R 的知识库、检索、纠错、维护、Skill 和 Agent 能力，默认先判断 GBrain 是否已有原生后处理能力；原始文件提炼已收口为 Project_R Agent / Skills 负责，GBrain 只接收 Project_R 生成的 Markdown source。原始资料进入 GBrain source 的具体操作流程见 `docs/gbrain-ingest-workflow.md`；Project_R 对 GBrain 的真实开发进度见 `docs/gbrain-adaptation-progress.md`；边界决策见 `docs/adr/0009-pr-owned-extraction-to-gbrain-markdown.md`、`docs/adr/0010-source-scoped-knowledge-ingest-review-policy.md` 和 `docs/adr/0011-automatic-extractor-routing-by-file-type.md`。

## 分类

| 分类 | 含义 |
|---|---|
| 直接沿用 | GBrain 已有成熟命令、operation、skill、recipe 或 schema 机制；Project_R 不重复实现核心逻辑。 |
| Adapter 包装 | GBrain 已有核心能力，但 Project_R 需要包一层权限、审计、路径、状态、UI 或通知。 |
| Skillify 补齐 | GBrain 没有完全覆盖 Project_R 的业务动作，但可以按 GBrain Skillify 思路补成可复用 skill。 |
| 暂不接入 | GBrain 有能力，但不是第一阶段需要，或接入成本/风险高。 |
| Project_R 保留 | 属于 Project_R 产品边界：用户、权限、审计、项目空间、原始文件保管、知识审核、桌面 UI。 |

## 边界原则

Project_R 保管原始文件、项目边界、用户权限、审计日志、回收站、知识审核和可视化工作台。GBrain 负责知识库内核：source、Markdown/frontmatter 系统记录、导入/同步、检索、综合回答、引用、图谱、维护、schema、skills、jobs 和 eval。Project_R 不直接依赖 GBrain 数据库表；正式业务调用默认通过 GBrain HTTP/MCP 常驻服务和 Project_R 后端 service account adapter 完成，CLI 只用于开发期初始化、诊断、人工运维和应急排障。

GBrain 是外部上游组件，不是 Project_R 自有代码。Project_R 后续不得无记录地直接修改 `reference/gbrain-master`；优先使用 GBrain 原生配置/command/operation/schema、Project_R adapter、以及更好的 `derived/` Markdown 结构解决后 Markdown 阶段的问题。原始文件提炼不要通过修改 GBrain 上游实现，而应做成 Project_R extractor skills。确实绕不开的 GBrain 源码改动必须记录到 `patches/gbrain/`，或升级为明确的 Project_R fork/submodule。当前维护决策见 `docs/adr/0008-gbrain-upstream-maintenance-policy.md`。

所有进入 GBrain 查询面的提炼型 Markdown 必须遵守 `bilingual_zh_en_aligned`：不论原始资料语言是中文、英文还是中英混合，最终知识页都要中英文并存，且两个语言版本表达同一事实，不能出现中英文信息不对称。原始 source record 可以保留原语言；提炼后沉淀为知识的页面必须双语对齐。

`workspace_data/` 是 Project_R 后端唯一资料源根目录。第一条竖切片使用：

```text
backend/workspace_data/global/company-wiki/
  raw/
  derived/    # GBrain company-wiki source repo; local Git enabled
  manifests/
```

其中 `raw/` 由 Project_R 或管理员保管原始资料；`derived/` 存放 Project_R 提炼后的 Markdown，并直接作为 GBrain `company-wiki` source repo；`manifests/` 存放 Project_R 侧的摄取状态、错误、来源映射和重跑记录。默认不手动编辑 `derived/`，也不另建一套 GBrain repo 再同步过去。`derived/` 启用本地 Git 版本记录，仅用于审计、对比和回滚，不默认配置远程仓库或上传 GitHub。

知识录入按 source scope 分责：管理员后台录入的公司知识视为管理员已自行检查，不需要额外审核；用户私人空间附件不得进入公司知识库；项目工作区资料由项目用户在文件面板点击“一键录入项目知识库”后只进入该项目 source，不流入 `company-wiki`。“未入库文件”的产品定义覆盖 Markdown/txt、DOCX、PDF、复杂 PDF、音频/视频、图片/截图、邮件和未来支持的业务附件。第一版一键录入会处理当前项目所有当前可处理且尚未入库的文件，并显示待录入数量；暂未完成 extractor 的类型保留为 `pending_extractor_capability`；完成或失败后通知触发用户。

用户只触发录入，不手动选择 API Key。Project_R 后端必须先识别 `file_kind`、`extraction_complexity` 和 `source_scope`，再自动选择 DeepSeek、MiMo、转写流程或 `pending_extractor_capability`；API Key 仍只存在于后端模型 provider 配置中。

## 功能矩阵

| 能力域 | GBrain 原生能力 | 原生入口 / 证据 | Project_R 接法 | 分类 | 备注 / 风险 |
|---|---|---|---|---|---|
| Brain / Source 模型 | 一个 brain 可包含多个 source；source 是同一 brain 内的内容仓库边界。 | `docs/architecture/brains-and-sources.md`；`sources_add/list/remove/status` operations。 | 一个 Project_R-managed brain；`company-wiki`、每个项目、未来用户私有空间分别映射为 source。 | Adapter 包装 | source id 需要稳定命名，避免项目改名导致历史引用漂移。 |
| 系统记录 | Markdown + frontmatter 是用户知识的系统记录，数据库是派生缓存。 | `docs/architecture/system-of-record.md`；`gbrain sync && gbrain extract all`。 | `derived/` 直接作为 GBrain 可索引的 Markdown source repo；Project_R `raw/` 是原始资料系统记录。 | 直接沿用 + Project_R 保留 | Project_R 原始文件和 GBrain 派生 Markdown 是两层系统记录，必须用 manifest 连接；不另建 GBrain repo。 |
| `derived/` 版本记录 | GBrain 推荐 Markdown repo 作为系统记录，天然适合 Git 版本化。 | `docs/architecture/system-of-record.md`。 | `derived/` 初始化为本地 Git repo；Project_R/GBrain adapter 在成功写入派生 Markdown 后提交本地 commit。 | Adapter 包装 | 不配置远程、不上传 GitHub；`backend/workspace_data/` 已被 Project_R 主仓库 `.gitignore` 忽略，嵌套 Git 属于运行数据版本层。 |
| 全局公司知识库 | source 可承载一个独立知识库。 | `gbrain sources add/list/status`；README company brain。 | 第一阶段仅接 `company-wiki` source，source path 绑定 `backend/workspace_data/global/company-wiki/derived/`。 | Adapter 包装 | 先跑通公司全局源，再扩展项目源。 |
| 项目知识库 | 同一 brain 多 source，天然适合项目隔离。 | `source_id` 多源导入、查询 scope；`.gbrain-source` 路由。 | 每个工作区/项目映射独立 project source；第一版 adapter 已使用 `project-{brand}-{workspace_id}` 稳定 source id、`derived/` 路径、显式 query scope 和项目文件编译 manifest。新规则要求项目文件面板一键录入当前项目所有未入库文件；可处理文件直接同步项目 source，缺 extractor 的音频/视频、图片/截图、邮件、复杂 PDF 标记为 `pending_extractor_capability`；不进入公司库、不走管理员审核。 | Adapter 包装 | Project_R 必须在查询时强制带 source scope，避免跨项目泄露；真实项目 one-click ingest/sync/query 闭环仍待完成。 |
| Markdown / code 导入与同步 | 支持 markdown/code import、sync、chunk、embedding、schema type 推断。 | `src/core/import-file.ts`；README `gbrain import` / `gbrain sync`。 | Project_R worker 将 `derived/` 中的 Markdown 交给 GBrain import/sync。 | 直接沿用 | 不在 Project_R 重写切片、embedding、Chroma fallback。 |
| 原始文件到 Markdown | GBrain 的 ingest/media/meeting/recipes/processor 可作为设计参考，但不作为 Project_R 生产链路的原始文件提炼拥有者。 | `skills/ingest`、`skills/media-ingest`、`skills/meeting-ingestion`、recipes、`src/core/ingestion/types.ts`。 | Project_R 根据文件类型、复杂度和业务场景调用自己的 extractor classifier / skills：DeepSeek 处理文字类原始资料和普通 PDF 证据文本，MiMo 处理复杂 PDF、视觉/版式/图片类资料，音视频先进入转写流程，邮件按线程解析；按 source scope 输出到公司或项目 `derived/`。 | Project_R 保留 + Adapter 包装 | 用户不选择 API Key，后端只记录 route/profile 和原因；GBrain 只接收 Project_R 产出的 Markdown 后再做 source sync、chunk、embedding、query/think/citation。私人空间附件不进入公司库；项目资料不流入 `company-wiki`。 |
| HTTP `/ingest` | 文本型 webhook ingest 已有；二进制 PDF/图片/音视频提示需要 content-type processor skillpack。 | `src/commands/serve-http.ts` `/ingest`。 | 第一阶段不要把复杂文件都直接丢 HTTP `/ingest`；优先文件型 worker + content-specific pipeline。 | Adapter 包装 | 需要把失败原因写入 `manifests/`，不能静默标记 indexed。 |
| Capture | 支持直接文本、stdin、文件捕获到 inbox 风格页面。 | README `gbrain capture`；`src/commands/capture.ts`。 | 可用于快速笔记、人工补充知识、复盘摘要入库。 | Adapter 包装 | capture 适合文本，不替代复杂资料解析。 |
| 检索 | 支持 keyword search、hybrid query、source-tier boost、RRF、reranker、graph signals。 | README `gbrain search` / `gbrain query`；`skills/query/SKILL.md`。 | Project_R `/query` 作为软件内“查询知识库”Skill 调用指令，调用 GBrain `query` 并强制传入允许的 `source_id`。 | 直接沿用 | 普通 Chat 不自动查 GBrain；旧 Wiki Router / Chroma 不再作为回退层；GBrain legacy bearer token 的 HTTP `search` 默认只读 `default` source，Project_R adapter 不使用裸 search 作为正式路径。 |
| 旧 RAG 退役 | Project_R 旧 `knowledge_base/wiki`、Wiki Router、Chroma/vector_store 是开发期遗留底座。 | 已删除旧 `core/wiki_router.py`、`core/rag_engine.py` 和对应旧测试。 | 不迁移旧索引，不把旧 `knowledge_base/wiki` 作为 GBrain 权威输入；由管理员重新投喂源文件生成 `company-wiki`。 | 已退役主路径 | 因软件仍在代码阶段且未正式使用，可以大胆废弃旧 RAG，降低双系统维护成本。 |
| 综合回答 | `think` 在检索基础上做综合回答、引用和 gap analysis。 | README `gbrain think`；operations `think`；`src/core/think/*`。 | 已完成 Project_R guarded adapter：`/query --think ...` 与 `/think ...` 可显式调用 GBrain MCP `think`，并把 citations/gaps/warnings 映射到来源面板；本地 patch `0003` 已补齐 `runGather()` 到 page/take/graph 检索流的 source scope 传递。2026-05-30 已用 `company-wiki` source-scoped OAuth client 跑通真实 MCP `think`，证明 token-bound source scope 生效；随后用 `deepseek:deepseek-chat` 完成综合回答与 citation 验证，并新增真实服务 `think` 回归脚本。默认仍关闭。 | 直接沿用 + Adapter 包装 + 临时上游 patch | `bun run typecheck` 与 `bun test test/takes-engine.test.ts test/think-pipeline.serial.test.ts` 已验证 takes keyword/vector 与 gather source scope；真实 MCP 调用在 `书面化原则是什么` 上返回 DeepSeek 答案、`warnings=[]`、`citations>=1`，`backend/scripts/gbrain_think_regression.py` 可重复验证。下一步需补项目 source think scope、扩展质量回归和前端 gap/conflict 展示。 |
| 引用溯源 | 每个事实应有 source attribution；冲突要并列展示。 | `docs/guides/source-attribution.md`；`skills/query/SKILL.md`。 | Project_R 右侧来源面板和知识审核沿用 GBrain citation。 | Adapter 包装 | 对公司资料，引用需要能回到 Project_R 原始文件或派生 Markdown。 |
| 错误答案修正 | GBrain 没有“按错答案一键修复”的单点功能；有 citation-fixer、maintain、contradiction probe、takes supersede/mark-debate、dream synthesize 等工具链。 | `skills/citation-fixer`、`skills/maintain`、`docs/contradictions.md`。 | Project_R 做“答案反馈 -> 定位引用 -> 判定是来源错误/过期/缺引用/冲突 -> 调用 GBrain 修复工具或进入审核”的工作流；当前已完成低分 GBrain 回答反馈生成 `KnowledgeReview`，并补了 citation-fixer agent 提交入口。 | Adapter 包装 + Skillify 补齐 | Skillify 是“把重复流程做成 skill”的元技能，不是直接纠错按钮；当前仍未自动事实覆盖，citation-fixer 真实执行还需要 agent OAuth/client/worker 验收。 |
| 引用修复 | citation-fixer 可审计和修复引用格式、缺失引用等。 | `skills/citation-fixer/SKILL.md`；resolver；MCP operation `submit_agent`。 | citation-fixer 不是 `submit_job` 的普通 job；Project_R 已新增 `GBrainAdapter.submit_citation_fixer()`、`POST /admin/knowledge/gbrain/citation-fixer` 和管理员 GBrain 维护区提交表单，按 GBrain `submit_agent` 路径提交 `subagent` 任务；维护状态显示非敏感 agent readiness。2026-05-30 已注册本机 agent-bound OAuth client、启用 DeepSeek gateway loop，并用 Project_R adapter 冒烟验证 `submit_agent` 绑定可创建 job；随后补齐 `patches/gbrain/0005-subagent-tool-source-scope.patch` 和 `patches/gbrain/0006-chat-tool-json-schema-wrapper.patch`，用 PGLite `jobs submit subagent --follow` 跑通 `company-wiki` source 内 `search/get_page` 只读 inline 执行。 | 直接沿用 + Adapter 包装 + 临时上游 patch | 修复引用不等于修正事实；`inline_execution_verified` 只证明 DeepSeek gateway-loop + 只读 subagent 可执行，真实 citation-fixer 改写型任务完成仍未验收；PGLite 阶段无持久 worker，长期生产更适合 Postgres worker。 |
| 冲突检测 | suspected-contradictions 是只读探针，输出疑似冲突和建议命令。 | `docs/contradictions.md`；operation `find_contradictions`。 | 管理员后台已展示 `find_contradictions` 最近结果；人工审核后再执行修正。 | Adapter 包装 | `find_contradictions` 不会主动生成探针结果，后续还要接定时 probe / eval job；不能自动把冲突当事实覆盖。 |
| 维护 / Doctor / Dream | health、doctor、remediate、dream、autopilot、extract links/timeline、embed stale。 | `skills/maintain/SKILL.md`；README；operations `run_doctor`、`run_onboard`。 | Project_R 管理员后台已显示健康分、maintain check、维护报告摘要，并允许触发 GBrain jobs。 | Adapter 包装 | 自动 remediation 仍需费用上限、权限边界和运行窗口；当前只开放 `run_onboard(mode=check)`。 |
| 图谱 / 自动链接 / Timeline | `put_page` 自动链接；extract links/timeline；graph-query；backlinks。 | `skills/query/SKILL.md`；`skills/maintain/SKILL.md`；operations graph/timeline。 | 项目复盘、关系查询、会议/邮件追踪优先用 GBrain graph/timeline。 | 直接沿用 | Project_R 不再用简单文本 chunk 模拟关系查询。 |
| Schema packs | 内置 schema packs，可 detect/suggest/review/apply；支持 agent-authored schema。 | README schema section；`schema_*` operations；`skills/schema-author`。 | 先用默认 `gbrain-base-v2`；后续为公司项目资料设计 Project_R schema pack。 | Adapter 包装 + Skillify 补齐 | 过早自定义 schema 会增加迁移成本；先用默认跑通。 |
| Skills / Resolver | 43 个左右 curated skills，resolver 负责触发和组合。 | `skills/RESOLVER.md`。 | Project_R Agent 功能先映射到 GBrain 原生 skills，业务 UI 只做入口和状态。 | 直接沿用 + Adapter 包装 | Project_R 自己的业务 Skill 与 GBrain skill 需要命名边界，避免重复。 |
| Skillify | 把重复功能补成正式 skill：SKILL.md、代码、测试、resolver、E2E、eval。 | `skills/skillify/SKILL.md`；`src/commands/skillify.ts`。 | 原始文件提炼优先做成 Project_R extractor skill；GBrain Skillify 后续只用于 GBrain 内部后处理能力或作为设计参考。 | Adapter 包装 / 暂缓 | 不用于一次性修答案；不要把 Project_R 原始文件生命周期重新交给 GBrain。 |
| Minions / Jobs | 持久化 job queue、subagents、shell jobs、progress、cancel/retry。 | README Minions；operations `submit_job`、`submit_agent`、`list_jobs`、`get_job_progress`、`cancel_job`、`retry_job`。 | Project_R 管理员后台已接入 jobs 列表、提交、取消、重试和通知；提交白名单仅允许 `sync/embed/lint/import/extract/backlinks/autopilot-cycle`，不开放 `shell`。citation-fixer 走 `submit_agent`，不混入普通 job 白名单。 | Adapter 包装 | 仍需真实 worker 长跑验收、任务完成轮询通知，以及 Project_R job id 与 GBrain job id 的长期映射。 |
| MCP / HTTP / OAuth / Scope | `gbrain serve --http` 提供 OAuth 2.1、read/write/admin scopes、MCP tools。 | README MCP；`src/commands/serve-http.ts`。 | 第一版已确认由 Project_R 后端 service account adapter 调用 GBrain HTTP/MCP 常驻服务；后续再评估用户级 OAuth/scope。 | Adapter 包装 | 用户级权限不能只依赖 GBrain scope，Project_R 项目权限仍是第一层。CLI 不作为正式业务调用主路径。 |
| 文件存储 | GBrain 有 files/status/verify、raw sidecars、storage tiering 等能力。 | `skills/maintain/SKILL.md` file storage health；`docs/storage-tiering.md`。 | 原始文件仍由 Project_R 管；GBrain 文件能力只作为派生资料/附件/sidecar 辅助。 | Project_R 保留 + 暂不接入 | 避免两套系统同时拥有同一个原始文件生命周期。 |
| 评测 / 搜索质量 | LongMemEval、eval export/replay、cross-modal eval、search benchmark。 | README eval framework；`docs/eval/*`；`skills/maintain/SKILL.md` benchmark。 | 已有第一版 Project_R 管理员质量回归入口：query 回归默认运行，Think 回归需显式 `include_think=true`，用于升级前和配置变更后验收。 | Adapter 包装 | 当前先覆盖公司真实样本的 query/think 回归；后续再接 GBrain eval/benchmark、项目 source 回归和更完整的质量报告。 |
| 邮件 / 会议 / 日历 / 语音 recipe | GBrain 有会议、邮件、voice、webhook recipes 和 ingestion skills，可作为 Project_R extractor skill 的参考。 | README integrations；recipes；`docs/integrations/*`；`skills/meeting-ingestion/SKILL.md`；`skills/voice-note-ingest/SKILL.md`。 | 项目会议、邮件、复盘资料由 Project_R extractor skills 负责提炼和归属；GBrain 接收按 source scope 写入的 Markdown。当前已先做音视频同名 transcript 侧车 adapter。 | Project_R 保留 + Adapter 包装 | 自动转录、公司邮件/聊天系统格式需要单独做 Project_R 适配；GBrain 后续负责 sync/query/think/citation/maintain。 |
| 图片 / 跨模态检索 | 支持 image import、多模态 embedding、`search_by_image` operation；OCR 可配置。 | `src/core/import-file.ts`；operations `search_by_image`。 | 后续用于项目图片/截图；第一阶段不作为公司 wiki 主路径。 | 暂不接入 | 截图质量、OCR、隐私和引用定位需要独立验收。 |
| 代码库检索 | 支持 code import、symbol/code edge、code retrieval ops。 | `src/core/import-file.ts` code path；operations code retrieval。 | Project_R 当前不是代码知识库产品，暂缓。 | 暂不接入 | 仅在未来做内部研发知识库时启用。 |

## 第一阶段接入切片

1. 功能盘点和边界确认：本文件作为决策入口。
2. GBrain 运行方式确认：正式业务采用 GBrain HTTP/MCP 常驻服务 + Project_R 后端 service account adapter；CLI 只用于开发期初始化、诊断、人工运维和应急排障。
3. 准备切片已实现：`core/gbrain.py` 读取配置，初始化 `backend/workspace_data/global/company-wiki/{raw,derived,manifests}`，初始化 `derived/` 本地 Git，并通过 `/health/gbrain` 暴露环境、GBrain 服务健康状态和 `company-wiki` source 注册检查。
4. `company-wiki` source 已在本机 GBrain PGLite brain 中注册：直接绑定 `backend/workspace_data/global/company-wiki/derived/`，该目录即 GBrain source repo。
5. 原始资料摄取 worker：扫描 `raw/` 或项目文件目录，先输出 `file_kind`、`extraction_complexity`、`extractor_profile` 和 `classifier_reason`，再按文件类型调用 Project_R extractor skills，产出 Markdown 到对应 source 的 `derived/`，状态写入 `manifests/`；DeepSeek 负责文字类提炼和普通 PDF 证据文本，MiMo 负责复杂 PDF、视觉/版式/图片类提炼，音视频先走转写流程。项目资料由项目文件面板一键触发，产品定义覆盖当前项目所有未入库文件；第一版对已实现 extractor 的类型执行入库，对音频/视频、图片/截图、邮件、复杂 PDF 等缺能力类型标记 `pending_extractor_capability`，完成或失败后通知触发用户；私人空间附件不进入公司库。
6. 索引同步：调用 GBrain import/sync，状态写回 Project_R 管理员后台。
7. 问答 adapter：Project_R 的知识库问答调用 GBrain query/think，前端展示引用、gap、冲突；第一版 adapter 已实现 `query(..., source_id=company-wiki)`。产品语义上，`/query` 是“查询知识库”Skill 调用指令，不影响普通 chatbot 对日常问题的回答。
8. 纠错闭环：用户反馈错误答案后，Project_R 建立审核项，定位引用和来源，再调用 citation-fixer、maintain、contradiction review 或 Skillify 后的 Project_R 专用修正流程。当前第一段已落地：低分且带 GBrain 引用的回答反馈会生成管理员知识纠错审核项；citation-fixer 已补 `submit_agent` 提交入口、管理员表单和 `backend/scripts/gbrain_agent_preflight.py` 预检；`patches/gbrain/0004-agent-bound-oauth-client-registration.patch` 已补齐 GBrain 侧绑定型 agent OAuth client 注册入口；`0005`/`0006` 已补齐 source scope 与 DeepSeek gateway-loop 执行兼容。真实 client 注册、gateway loop、submit_agent 绑定和 PGLite 只读 inline 执行已验收；真实 citation-fixer 改写型执行仍待审核保护的测试页或 Postgres worker 长跑验收。

本节只描述能力边界和切片顺序；文件进入 `raw/`、如何生成 `derived/`、GBrain import/sync 的职责、PDF/音视频如何提炼，统一以 `docs/gbrain-ingest-workflow.md` 为准。

## 2026-05-28 本机准备状态

- `reference/gbrain-master` 版本为 `0.41.26.0`；Windows 下普通 `bun install` 会被类 Unix `postinstall` 脚本拦截，本机使用 `bun install --frozen-lockfile --ignore-scripts` 完成依赖检查。
- GBrain 运行目录固定为 `GBRAIN_HOME=backend/workspace_data/global/company-wiki`；GBrain 实际配置和 PGLite 数据库位于 `backend/workspace_data/global/company-wiki/.gbrain/`，仍在 `workspace_data/` 资料根下，不进入主 Git。
- 本机已在 2026-05-29 按 GBrain PGLite 路径切换到本地免费 embedding：`gbrain reinit-pglite --embedding-model ollama:mxbai-embed-large --embedding-dimensions 1024`，当前 schema pack 为 `gbrain-base-v2`。Ollama 已安装并拉取 `mxbai-embed-large`，真实 embedding 已生成。
- 本机已执行 `gbrain sources add company-wiki --path backend/workspace_data/global/company-wiki/derived --name "Project_R Company Wiki" --federated`。
- 本机 GBrain HTTP/MCP 服务可用：`gbrain serve --http --port 3131 --bind 127.0.0.1`，`/health` 返回 `status=ok`、`engine=pglite`。
- Project_R `/health/gbrain` 已能在配置 service bearer token 时通过 GBrain HTTP/MCP 调用 `sources_status`，并返回 `company-wiki` 的 `registered=true`、`path_matches=true`。没有 token 时返回 `auth_required`，这是权限配置待完成，不代表 source 未注册。该健康检查还读取本地 `.gbrain/config.json` 并返回非敏感 embedding 状态；当前本机为 `semantic_search_ready=true`、`model=ollama:mxbai-embed-large`、`dimensions=1024`、`provider_configured=true`。
- `sources_status` 对当前本地 `derived/` 返回 `clone_state=corrupted`，原因是 GBrain 的 clone 诊断要求本地 Git repo 存在 `origin` remote；Project_R 的 `derived/` 是无远程本地审计 repo。GBrain `sync` 对无 `remote_url` 的本地 source 会跳过 pull、走本地工作树同步，因此该诊断不等于 source 注册失败。
- 当 GBrain PGLite 服务运行时，本地 CLI 直接读同一 brain 可能因连接锁超时；正式业务和健康检查必须优先走 HTTP/MCP，CLI 只保留为服务停止状态下的初始化和运维工具。
- `reference/gbrain-master` 当前不是独立 Git 仓库、fork 或 submodule；本机为了验证 Ollama + `mxbai-embed-large` 和 GBrain `think` source scope 曾直接改过上游源码。该状态存在升级维护风险，当前三处改动已转为 `patches/gbrain/` 下的显式 patch 记录；升级 GBrain 前必须审计这些 patch 是否继续需要。

## 2026-05-28 真实样本验收记录

Gary 已将第一批真实样本放入 `backend/workspace_data/global/company-wiki/raw/`。本次验证没有使用合成测试文档。

原始样本：

1. 4 个 Markdown：`书面化原则.md`、`VMU 标准作业流程.md`、`VMU客户参观接待流程.md`、`VMU流程.md`。
2. 1 个 DOCX：`张学辉发起的视频会议_0515.docx`。
3. 2 个 PDF：`AS 1288-2006 Glass in buildings - Selection and installation.pdf`、`AS_2047-2014_Windows_and_external_glazed_doors_in_buildings.pdf`。
4. 1 个 MP3：`张学辉发起的视频会议_0515.mp3`。

处理结果：

- Project_R 新增 `core/gbrain_ingest.py` 作为窄口 adapter：扫描 `raw/`，将 Markdown/DOCX/PDF 编译为 GBrain 可导入 Markdown，输出到 `derived/`，并写入 `manifests/company-wiki-ingest-manifest.json`。
- 编译结果为 8 个源文件中 7 个成功、1 个跳过、0 个失败；MP3 因未配置音频转写链路而保留在 raw，并在 manifest 中记录跳过原因。
- `derived/` 本地 Git 已记录本次编译提交，提交说明为 `Compile company-wiki sources (7 compiled, 1 skipped, 0 failed)`。
- GBrain import 已执行：`imported=7`、`skipped=0`、`errors=0`、`chunks=192`。由于当前没有 embedding provider，本次使用 `--no-embed`。
- GBrain 对两个 PDF 标准文件和一个会议 DOCX 产生 content-sanity 大文件警告；后续应按标准章节、会议主题或行动项拆分，提升检索粒度和引用可读性。
- GBrain `get_stats` 返回 `page_count=7`、`chunk_count=192`、`embedded_count=0`、`pages_by_type={rule:4, reference:2, meeting:1}`。
- Project_R `GBrainAdapter.query()` 已通过 MCP `query` 工具显式传入 `source_id=company-wiki`，真实检索验证命中：
  - `书面化原则` -> `rules/书面化原则`
  - `VMU` -> `rules/vmu流程`、`rules/vmu-标准作业流程`
  - `Glass` -> `standards/as-1288-2006-glass-in-buildings-selection-and-installation`

2026-05-29 清退更新：

- 两个 PDF 纯文本抽取页面已从 `derived/standards/` 删除，并提交到 `derived/` 本地 Git。
- 两个 PDF 页面已从 GBrain `company-wiki` 中软删除并立即 purge：`standards/as-1288-2006-glass-in-buildings-selection-and-installation`、`standards/as_2047-2014_windows_and_external_glazed_doors_in_buildings`。
- 当前 `company-wiki` `page_count=5`；`Glass` 和 `AS 2047` 查询不再命中；`VMU` 与 `书面化原则` 查询仍正常命中。
- 当前 manifest 为 `total=8`、`compiled=5`、`skipped=3`、`failed=0`；两个 PDF 和一个 MP3 均为 skipped，等待结构化提炼或转写流程。

2026-05-29 PDF 结构化提炼 MVP 更新：

- 新增 `core/pdf_structured_extraction.py`，PDF 默认仍不纯文本直入库；显式启用后先用 `pypdf` 读取全文文本作为中间材料，再用 MiMo 视觉模型读取 PDF 同名 PNG 侧车文件夹中的关键页图，合成可审阅 Markdown。
- 新增硬性语言规则：PDF 结构化输出必须标记 `language_policy: bilingual_zh_en_aligned`，并在标题、核心结论、关键参数、业务建议、风险边界和待审核问题中保持中英文同义对齐；若模型输出明显不满足双语结构，提炼流程失败，不写入 GBrain-derived Markdown。
- MiMo 视觉验证使用 `mimo-v2.5`；`mimo-v2.5-pro` 当前不再默认标记为视觉模型，因为真实调用返回过图片输入 endpoint 不支持。
- PDF 侧车图片目录已接入扫描过滤：`raw/{PDF同名文件夹}/p001.png...` 用于视觉辅助，不作为独立 raw 文件进入 manifest。单独放在 raw 根目录的图片仍会被跳过，等待图片/截图提炼流程。
- 两份真实 PDF 已重新生成结构化 Markdown，后续又按 `bilingual_zh_en_aligned` 规则重跑为中英文对齐版本：
  - `AS 1288-2006 Glass in buildings - Selection and installation.pdf`：153/153 页文本，视觉页 `1, 6, 8, 39, 77, 90, 112, 115`。
  - `AS_2047-2014_Windows_and_external_glazed_doors_in_buildings.pdf`：73/73 页文本，视觉页 `1, 5, 14, 15, 18, 19, 37, 55`。
- 当前 manifest 为 `total=9`、`compiled=7`、`skipped=2`、`failed=0`；跳过项为根目录单张 PNG 与 MP3。
- GBrain sync 已在 Ollama embedding 下重新执行；2026-05-30 PGLite 重建并重新 sync 后，`company-wiki` 为 `page_count=7`、`chunks_total=207`、`chunks_unembedded=0`，已生成 `ollama:mxbai-embed-large / 1024` 向量。
- Hybrid/vector 查询验证：受控英文业务检索词可命中 AS 1288、AS 2047；Project_R 适配层会对中文 `/query` 同时运行受控英文业务检索词并按分数合并结果。现场验证 `安全玻璃有哪些要求` 首位命中 AS 1288，`窗户防水等级有哪些要求` 首位命中 AS 2047，`热浸测试适用于什么玻璃` 首位命中 AS 1288，`VMU客户参观接待流程是什么` 首位命中 VMU 客户参观接待流程。

当前未闭环项：

1. GBrain 已接入本地 Ollama embedding；管理员状态面板、启动/重启、raw 导入并同步、知识审核闭环已接入；查询质量回归集已建立第一版，覆盖 AS 1288、AS 2047、VMU、0515 会议和书面化原则。后续仍需扩展更多真实问题，并基于回归结果评估是否追加本地 reranker。
2. MP3 需要接入 GBrain voice-note/transcription 路径或 Project_R 音频转写 adapter；本机未安装 `ffmpeg`，也未配置 Groq/OpenAI 转写 key。
3. PDF 结构化提炼 MVP 默认输出到 `pending_review`，已接入管理员知识审核闭环；本次 AS 1288 / AS 2047 样本已标记为 `approved` 后进入查询面。逐条条款回链、图表全量视觉/OCR 校验和章节级拆页策略尚未完成。
4. GBrain legacy bearer token 的 HTTP `search/list_pages` 默认 source 为 `default`，不能直接看到 `company-wiki`；Project_R 正式查询必须走 `query` 并显式传 `source_id`，或后续改用带 source scope 的 OAuth client。

## 第一批文件类型验证顺序

这是第一阶段的工程验证顺序，不代表长期业务价值排序。排序依据是转换损耗、GBrain 原生路径贴合度、端到端闭环速度、业务资料价值和错误排查难度。

1. Markdown / txt：最接近 GBrain 的 Markdown/frontmatter 系统记录，优先用于跑通 `raw -> derived -> source -> query/think -> 引用展示 -> 管理员状态` 主链路。
2. PDF：公司合同、报价、技术资料价值高，但默认不直接入库；先进入待提炼状态，通过模型/视觉辅助结构化提炼后再进入 `derived/`。
3. 会议转写文本：已是文本，但需要验证会议结论、行动项和项目事件提炼。
4. 录音：需要先转写再提炼，错误链路更长。
5. 图片 / 截图：依赖 OCR 或视觉理解，引用定位和纠错更难。
6. 邮件导出：业务价值高，但线程、附件、权限、隐私和格式差异更复杂，第一阶段不作为主链路起点。

## 第一阶段验收样本

验收样本由 Gary 手动放入 `backend/workspace_data/global/company-wiki/raw/`。Agent 不凭空生成测试文档，也不使用合成资料冒充真实业务资料。

建议最小样本范围：

1. 3 个 Markdown / txt 文件，用于验证最小主链路。
2. 2 个 PDF 文件，用于验证 PDF 解析质量和引用回溯。
3. 1 份会议转写文本，用于验证会议结论、行动项和项目事件提炼。

验收重点是证明 `raw -> derived -> GBrain source -> query/think -> 引用展示 -> 管理员状态` 链路可用。

## 旧 RAG 退役记录

删除旧 RAG 相关代码前置条件：GBrain `company-wiki` source 已注册，`import/sync` 链路可用，`/query` 或等价知识库问答入口已改走 GBrain adapter，并能展示引用和健康状态。当前这些正式路径前置条件已满足，旧主路径已退役。

退役范围：

1. 聊天检索路径：已移除 `api/chat.py` 中对 `RAGEngine`、`WikiRouter`、`_search_rag_sources`、`_search_wiki_sources` 的依赖，改为 GBrain adapter。
2. 旧 API：已替换 `api/rag.py`，当前 `/admin/knowledge/*` 是 GBrain 管理接口。
3. 旧核心：已删除 `core/rag_engine.py` 与 `core/wiki_router.py`。
4. 旧运行数据：不再使用 `backend/vector_store/` 和 `backend/knowledge_base/wiki/` 作为知识库来源。
5. 旧测试：`test_rag_api.py` 和聊天主路径测试已改写为 GBrain；`test_rag_engine_phase10a.py`、`test_wiki_router.py` 已删除。
6. 旧依赖：正式配置项已从 `.env.example` 移除；`requirements.txt` 已移除 `chromadb`、`sentence-transformers`。
7. 审核写入点：已迁移到 GBrain source 的派生 Markdown 路径。新规则要求管理员公司知识直接进入 `company-wiki/derived/`，项目工作区资料由用户一键录入到对应项目 source，不进入公司库；审核队列保留给答案反馈纠错、显式提升公司知识和异常情况。
8. 前端和文档：用户可见主路径已改为 GBrain 知识库状态与来源引用。

删除原则：不做旧索引迁移，不保留 Chroma fallback，不把旧 `knowledge_base/wiki` 当作 GBrain 权威输入。

## 下一批需要继续对齐的问题

1. GBrain `think` 是否纳入 Project_R `/query` 的最终回答层：Project_R 已有 guarded adapter、显式 `/query --think` 入口、本地上游 `think` source-scope patch，并已完成 `company-wiki` source-scoped OAuth + MCP 服务链路、DeepSeek 综合回答、citations 和第一条真实服务回归验收。下一步需要补项目 source 的 OAuth/scope 验证、扩展 `think` 答案质量回归、gap/conflict 展示，再决定是否提升为 `/query` 默认回答层。
2. 项目级 source 映射：adapter 和项目文件编译第一版已完成稳定 source id、路径、状态展示、manifest、查询 source scope；下一步把现有项目 pending review 默认路径改为项目文件面板“一键录入项目知识库”，定义覆盖当前项目所有未入库文件，并对缺 extractor 的音频/视频、图片/截图、邮件、复杂 PDF 标记 `pending_extractor_capability`，再用真实项目文件跑通 one-click ingest/derived/sync/query/通知。
3. 音视频转写与会议提炼：接入 GBrain voice-note/transcription 路径或 Project_R adapter，并定义口音、多语言、术语纠错和人工抽检流程。
