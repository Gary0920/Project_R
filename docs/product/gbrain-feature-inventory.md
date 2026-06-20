# GBrain 功能盘点矩阵

状态：v0.1，Project_R 接入 GBrain 前置盘点。  
来源：本地 `reference/gbrain-master`，`package.json` 版本 `0.42.51.0`，以及 GBrain README、docs、skills、`src/core/operations.ts` 等源码。
目的：后续 Project_R 的知识库、检索、纠错、维护、Skill 和 Agent 能力，默认先判断 GBrain 是否已有原生后处理能力；原始文件提炼已收口为 Project_R Agent / Skills 负责，GBrain 只接收 Project_R 生成的 Markdown source。原始资料进入 GBrain source 的具体操作流程见 `docs/specs/gbrain-ingest-workflow.md`；Project_R 对 GBrain 的真实开发进度见 `docs/milestones/gbrain-adaptation-progress.md`；边界决策见 `docs/adr/0009-pr-owned-extraction-to-gbrain-markdown.md`、`docs/adr/0010-source-scoped-knowledge-ingest-review-policy.md` 和 `docs/adr/0011-automatic-extractor-routing-by-file-type.md`。

2026-06-20 升级状态：GBrain `0.42.51.0` 已完成本地正式切换，`reference/gbrain-master` 来自验证过的 `reference/gbrain-upstream-0.42.51` candidate，候选 commit 为 `9bf96db807c2f050449142f2f0b05726f58e5054`。`0001`、`0002`、`0003`、`0004`、`0005` 已 rebased，`0006` 已被 upstream absorbed，`0007` 已 rebased 但与 `0003` 在 `think/gather` 有维护重叠，`0008` 修复 Windows CRLF 下 doctor resolver false failure。切换后 `/health` 返回 `version=0.42.51.0`、`engine=pglite`，`doctor --fast --json` 为 warnings-only，`resolver_health=ok`。证据见 `docs/validation/gbrain-upgrade-0.42.51-cutover.md`、`docs/validation/gbrain-upgrade-0.42.51-switch-decision.md` 和 `docs/operations/gbrain-upgrade-0.42.51-cutover-runbook.md`。

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
  raw/        # 原始源文件
  ...
_preprocessed/
  company/company-wiki/
    gbrain-ready/  # GBrain company-wiki source repo
    runs/
    manifests/
```

其中用户源文件目录只保存原始资料；Project_R 预处理过程文件写入 `_preprocessed/.../runs/`，最终 Markdown 写入 `_preprocessed/.../gbrain-ready/` 并作为 GBrain source repo，`manifests/` 存放 Project_R 侧的摄取状态、错误、来源映射和重跑记录。旧 `workspace_data/.../derived/` 是早期 MVP 实现，不再作为目标架构扩展方向。

知识录入按 source scope 分责：管理员后台录入的公司知识视为管理员已自行检查，不需要额外审核；个人工作台附件不得进入公司知识库；项目工作区资料只进入当前项目 source，不流入 `company-wiki`；客户工作区资料只进入受限客户情报数据范围。文件面板“录入”默认处理当前打开路径并递归子文件夹，必须二次确认；右键菜单提供“录入此文件”。暂未完成 extractor 的类型保留为 `pending_capability`；完成或失败后通知触发用户。

用户只触发录入，不手动选择 API Key。Project_R 后端必须先识别 `file_kind`、`extraction_complexity` 和 `source_scope`，再自动选择 DeepSeek、MiMo V2.5、转写流程或 `pending_capability`；API Key 仍只存在于后端模型 provider 配置中。纯文本使用 DeepSeek；PDF、截图、图纸、设计图片和视觉版式资料统一使用 MiMo V2.5，不使用 MiMo V2.5 Pro；PDF 文本抽取只能作为辅助证据。

## 功能矩阵

| 能力域 | GBrain 原生能力 | 原生入口 / 证据 | Project_R 接法 | 分类 | 备注 / 风险 |
|---|---|---|---|---|---|
| Brain / Source 模型 | 一个 brain 可包含多个 source；source 是同一 brain 内的内容仓库边界。 | `docs/architecture/brains-and-sources.md`；`sources_add/list/remove/status` operations。 | 一个 Project_R-managed brain；`company-wiki`、每个项目、未来用户私有空间分别映射为 source。 | Adapter 包装 | source id 需要稳定命名，避免项目改名导致历史引用漂移。 |
| 系统记录 | Markdown + frontmatter 是用户知识的系统记录，数据库是派生缓存。 | `docs/architecture/system-of-record.md`；`gbrain sync && gbrain extract all`。 | `_preprocessed/.../gbrain-ready/` 作为 GBrain 可索引的 Markdown source repo；Project_R 用户源文件目录是原始资料系统记录。 | 直接沿用 + Project_R 保留 | Project_R 原始文件和 GBrain-ready Markdown 是两层系统记录，必须用 manifest 连接；不在源文件目录内创建 `derived/`。 |
| GBrain-ready 版本记录 | GBrain 推荐 Markdown repo 作为系统记录，天然适合 Git 版本化。 | `docs/architecture/system-of-record.md`。 | 目标是对 `gbrain-ready/` 或等价 manifest/audit-log 机制做审计、对比和回滚；早期 `derived/` 本地 Git 仅为 MVP。 | Adapter 包装 | 不配置远程、不上传 GitHub；`backend/workspace_data/` 已被 Project_R 主仓库 `.gitignore` 忽略，运行数据版本层不得混入应用仓库。 |
| 全局公司知识库 | source 可承载一个独立知识库。 | `gbrain sources add/list/status`；README company brain。 | `company-wiki` 目标 source path 绑定 `backend/workspace_data/_preprocessed/company/company-wiki/gbrain-ready/`；当前 `derived/` 是 MVP 旧路径。 | Adapter 包装 | 先跑通公司全局源，再扩展项目源。 |
| 项目知识库 | 同一 brain 多 source，天然适合项目隔离。 | `source_id` 多源导入、查询 scope；`.gbrain-source` 路由。 | 每个工作区/项目映射独立 project source；source id 仍用 `project-{brand}-{workspace_id}`，目标 path 为 `_preprocessed/project/{brand}/{workspace_id}-{project_slug}/gbrain-ready/`。文件面板“录入”处理当前打开路径并递归确认；右键支持单文件录入；缺 extractor 的类型标记为 `pending_capability`；不进入公司库、不走管理员审核。 | Adapter 包装 | Project_R 必须在查询时强制带 source scope，避免跨项目泄露；等待 Gary 新建测试项目后重新跑真实 ingest/sync/query/think 回归。 |
| 客户情报 / 客户画像 source | 同一 brain 的统一受限客户情报数据范围可承载 CRM 客户业务情报；GBrain Entity Enrichment、graph、timeline、think 适合 People Graph、Company Graph、Project Graph、人物画像和沟通脉络。 | 受限 customer intelligence source scope、OAuth source scope、graph/timeline、citations、Project_R 工作区权限。 | 已确认 `workspace_data/customer/` 是 CRM 客户画像资料根，不是项目目录；主要保存客户邮件、会议、联系人、公司、项目关系、沟通事件和销售判断线索。客户画像是受限业务情报，不是公司公共知识库；不得写入 `company-wiki`，客户 `/query` 也不叠加 `company-wiki` 或项目 source。`customer-reference` 只视为早期统一客户情报 source id，不是产品层术语。Project_R `customer` 工作区负责权限入口：系统管理员可新建客户情报工作区，默认隐藏，普通用户必须由成员或组别授权后才能搜索/进入。图片/ZIP/Excel 等客户复杂资料只保留 pending 状态，不污染 GBrain。 | Adapter 包装已起步 / 待产品化 | 仅营销组或授权成员可查；不能污染公司规章和行业知识；当前 goal 不要求完成客户复杂资料 extractor；People/Company/Project Graph 质量、native timeline 可视化增强、正文级实体合并/删除审核和客户/项目/公司临时联合查询规则仍需单独设计。 |
| Markdown / code 导入与同步 | 支持 markdown/code import、sync、chunk、embedding、schema type 推断。 | `src/core/import-file.ts`；README `gbrain import` / `gbrain sync`。 | Project_R worker 将 `gbrain-ready/` 中的 Markdown 交给 GBrain import/sync。 | 直接沿用 | 不在 Project_R 重写切片、embedding、Chroma fallback。 |
| 原始文件到 Markdown | GBrain 的 ingest/media/meeting/recipes/processor 可作为设计参考，但不作为 Project_R 生产链路的原始文件提炼拥有者。 | `skills/ingest`、`skills/media-ingest`、`skills/meeting-ingestion`、recipes、`src/core/ingestion/types.ts`。 | Project_R 根据文件类型、复杂度和业务场景调用自己的独立 preprocessor Skills：DeepSeek 处理文字类原始资料，MiMo V2.5 处理 PDF、视觉/版式/图片类资料，音视频先进入转写流程，邮件按线程解析；按 source scope 输出到对应 `gbrain-ready/`。 | Project_R 保留 + Adapter 包装 | 用户不选择 API Key，后端只记录 route/profile 和原因；GBrain 只接收 Project_R 产出的 Markdown 后再做 source sync、chunk、embedding、query/think/citation。个人工作台附件不进入公司库；项目资料不流入 `company-wiki`。 |
| HTTP `/ingest` | 文本型 webhook ingest 已有；二进制 PDF/图片/音视频提示需要 content-type processor skillpack。 | `src/commands/serve-http.ts` `/ingest`。 | 第一阶段不要把复杂文件都直接丢 HTTP `/ingest`；优先文件型 worker + content-specific pipeline。 | Adapter 包装 | 需要把失败原因写入 `manifests/`，不能静默标记 indexed。 |
| Capture | 支持直接文本、stdin、文件捕获到 inbox 风格页面。 | README `gbrain capture`；`src/commands/capture.ts`。 | 可用于快速笔记、人工补充知识、复盘摘要入库。 | Adapter 包装 | capture 适合文本，不替代复杂资料解析。 |
| 检索 | 支持 keyword search、hybrid query、source-tier boost、RRF、reranker、graph signals。 | README `gbrain search` / `gbrain query`；`skills/query/SKILL.md`。 | Project_R 不再把裸 query 作为用户最终回答层；`/query` 统一走 GBrain native `think`，由 GBrain 内部调用最合适的检索和综合链路。 | 直接沿用 | 普通 Chat 不自动查 GBrain；旧 Wiki Router / Chroma 不再作为回退层；GBrain legacy bearer token 的 HTTP `search` 默认只读 `default` source，Project_R adapter 不使用裸 search 作为正式用户路径。 |
| 旧 RAG 退役 | Project_R 旧 `knowledge_base/wiki`、Wiki Router、Chroma/vector_store 是开发期遗留底座。 | 已删除旧 `core/wiki_router.py`、`core/rag_engine.py` 和对应旧测试。 | 不迁移旧索引，不把旧 `knowledge_base/wiki` 作为 GBrain 权威输入；由管理员重新投喂源文件生成 `company-wiki`。 | 已退役主路径 | 因软件仍在代码阶段且未正式使用，可以大胆废弃旧 RAG，降低双系统维护成本。 |
| 综合回答 | `think` 在检索基础上做综合回答、引用和 gap analysis。 | README `gbrain think`；operations `think`；`src/core/think/*`。 | 已完成 Project_R guarded adapter：`/query ...` 直接调用 GBrain MCP `think`；citations 映射为聊天来源项，gaps/conflicts/warnings 写入 `context_trace.gbrain_think` 并在前端“本轮上下文”卡片展示。2026-06-02 已补审核提交 MVP：带 gap/conflict/warning 的回答可提交 `gbrain_think_review:*` 知识审核项，管理员后台可继续用知识审核和 citation-fixer 处理。同日已补质量报告存档/趋势/导出 MVP：管理员 query/Think 回归结果保存到 `gbrain-quality-reports.json`，状态接口和 GBrain 面板显示最近报告、最近 5 次趋势，并可导出单份 JSON 报告。本地 patch `0003` 已补齐 `runGather()` 到 page/take/graph 检索流的 source scope 传递。2026-05-30 已用 `company-wiki` source-scoped OAuth client 跑通真实 MCP `think`，证明 token-bound source scope 生效；随后用 `deepseek:deepseek-chat` 完成综合回答与 citation 验证，并新增真实服务 `think` 回归脚本。2026-06-01 已补项目 source 专属 OAuth client manifest 与自动注册，项目 source 不再要求手工加入全局 allowlist。 | 直接沿用 + Adapter 包装 + 临时上游 patch | `bun run typecheck` 与 `bun test test/takes-engine.test.ts test/think-pipeline.serial.test.ts` 已验证 takes keyword/vector 与 gather source scope；真实 MCP 调用在 `书面化原则是什么` 上返回 DeepSeek 答案、`warnings=[]`、`citations>=1`，`backend/scripts/gbrain_think_regression.py` 可重复验证。下一步需用新测试项目跑项目 source Think 回归，并扩展客户 source 回归。 |
| 引用溯源 | 每个事实应有 source attribution；冲突要并列展示。 | `docs/guides/source-attribution.md`；`skills/query/SKILL.md`。 | Project_R 右侧来源面板和知识审核沿用 GBrain citation。 | Adapter 包装 | 对公司资料，引用需要能回到 Project_R 原始文件或派生 Markdown。 |
| 错误答案修正 | GBrain 没有“按错答案一键修复”的单点功能；有 citation-fixer、maintain、contradiction probe、takes supersede/mark-debate、dream synthesize 等工具链。 | `skills/citation-fixer`、`skills/maintain`、`docs/contradictions.md`。 | Project_R 做“答案反馈 -> 定位引用 -> 判定是来源错误/过期/缺引用/冲突 -> 调用 GBrain 修复工具或进入审核”的工作流；当前已完成低分 GBrain 回答反馈生成 `KnowledgeReview`，并补了 GBrain Think gap/conflict/warning 直接提交审核项、citation-fixer agent 提交入口、job 追踪、worker 轮询和管理员从 GBrain 审核项受控提交 citation-fixer 的入口。 | Adapter 包装 + Skillify 补齐 | Skillify 是“把重复流程做成 skill”的元技能，不是直接纠错按钮；citation-fixer 真实 PGLite inline 改写、低分审核和 GBrain Think 审核受控触发已验收，但仍不自动覆盖事实、不自动通过审核，也未做事实级自动修正。 |
| 引用修复 | citation-fixer 可审计和修复引用格式、缺失引用等。 | `skills/citation-fixer/SKILL.md`；resolver；MCP operation `submit_agent`。 | citation-fixer 不是 `submit_job` 的普通 job；Project_R 已新增 `GBrainAdapter.submit_citation_fixer()`、`POST /admin/knowledge/gbrain/citation-fixer` 和管理员 GBrain 维护区提交表单，按 GBrain `submit_agent` 路径提交 `subagent` 任务；维护状态显示非敏感 agent readiness。2026-05-30 已注册本机 agent-bound OAuth client、启用 DeepSeek gateway loop，并用 Project_R adapter 冒烟验证 `submit_agent` 绑定可创建 job；随后补齐 `patches/gbrain/0005-subagent-tool-source-scope.patch` 和 `patches/gbrain/0006-chat-tool-json-schema-wrapper.patch`，用 PGLite `jobs submit subagent --follow` 跑通 `company-wiki` source 内 `search/get_page` 只读 inline 执行。2026-06-02 已补并通过 `backend/scripts/gbrain_agent_citation_fixer_mutation_smoke.py` 真实改写型 smoke：合成测试页限定 `reviews/citation-fixer-smoke/*` 写入 glob，GBrain subagent job `#172` 用 `put_page` 修复 Citation 行；Project_R 将 GBrain 非 default source sidecar 同步回正式 `derived/` 文件并提交本地 Git `8a3ace3`，随后写入 `GBRAIN_AGENT_EXECUTION_VERIFIED=true`。同日继续补管理员 job 追踪 MVP：提交后记录 `gbrain-citation-fixer-jobs.json`，`POST /admin/knowledge/gbrain/citation-fixer/poll-jobs` 可轮询 GBrain job、同步 sidecar、提交 derived Git、通知管理员；Project_R 维护 worker 已接入 citation-fixer tracked jobs 自动轮询，管理员面板显示 tracking 摘要和“轮询引用修复”按钮。随后新增 `POST /admin/knowledge-reviews/{review_id}/citation-fixer` 和知识审核列表“引用修复”按钮，管理员可从 `gbrain_answer_correction:*` 低分审核项直接提交受控 citation-fixer，系统推断 page slug、默认限制同目录 slug prefix，并阻止重复活跃 job。随后补单任务回滚 MVP：同步成功时记录 Git commit hash，`POST /admin/knowledge/gbrain/citation-fixer/{job_id}/rollback` 和管理员面板“回滚”按钮可撤销该 job 写入，写审计、通知并清理 sidecar。 | 直接沿用 + Adapter 包装 + 临时上游 patch | 修复引用不等于修正事实；PGLite inline 改写、管理员轮询同步、Project_R worker 轮询、低分审核受控触发和单任务回滚已验收，但 GBrain 原生 Postgres worker 长跑未验收；仍需批量修复费用/权限边界、批量/冲突状态恢复策略和事实级自动修正策略。 |
| 冲突检测 | suspected-contradictions 是只读探针，输出疑似冲突和建议命令。 | `docs/contradictions.md`；operation `find_contradictions`；CLI `eval suspected-contradictions run`。 | 管理员后台已展示 `find_contradictions` 最近结果；2026-06-02 已补 Project_R-side contradiction probe 配置、手动运行、到期 tick、维护 worker 自动触发和管理员面板状态。探针通过 GBrain 原生 CLI `eval suspected-contradictions run --queries-file ... --json --yes` 生成疑似冲突，再刷新 `find_contradictions` 展示；人工审核后再执行修正。 | Adapter 包装 | 只读探针不等于事实修正；当前不会自动覆盖事实。GBrain 原生 CLI 当前没有显式 source scope 参数，Project_R 只用受控查询列表和公司 brain 级预算运行，不把它当项目/客户 source 的自动纠错器。 |
| 维护 / Doctor / Dream | health、doctor、remediate、dream、autopilot、extract links/timeline、embed stale。 | `skills/maintain/SKILL.md`；README；operations `run_doctor`、`run_onboard`、`submit_job`。 | Project_R 管理员后台已显示健康分、maintain check、维护报告摘要，并允许触发 GBrain jobs。2026-06-02 已补 Dream Cycle 计划配置 manifest、管理员启停/周期/source/job 列表、手动运行和运行结果记录，默认可提交 `autopilot-cycle` 白名单 job；同日继续补 worker-callable `tick` 与 `poll-jobs`，记录 Dream Cycle 自己提交的 tracked jobs，并在完成/失败终态写通知中心，管理员面板可手动检查到期和轮询任务；同日再补 FastAPI 后台 worker 挂载，按 `PR_GBRAIN_MAINTENANCE_WORKER_INTERVAL_SECONDS` 周期运行 Dream tick/poll、citation-fixer poll 和 contradiction probe tick，管理员维护状态展示 worker 心跳、citation-fixer 最近检查结果、冲突探针最近结果并可重启。随后补 worker 异常通知/审计最小闭环：后台维护 tick 抛异常时会记录 `last_error`、通知系统管理员并写入失败审计。随后补管理员 Worker 诊断卡，展示启停、心跳、运行次数、最近错误和各子链路最近状态。 | Adapter 包装 | 自动 remediation 仍需费用上限、权限边界和运行窗口；当前已有计划、手动运行、到期触发 API、任务轮询通知、后台 worker MVP、异常通知审计、只读冲突探针调度和 UI 诊断卡，但 GBrain 原生 Postgres worker 长跑、运行窗口/费用上限策略仍未完成。 |
| 图谱 / 自动链接 / Timeline | `put_page` 自动链接；extract links/timeline；graph-query；backlinks。 | `skills/query/SKILL.md`；`skills/maintain/SKILL.md`；operations `get_links/get_backlinks/traverse_graph/get_timeline`；CLI `graph-query`、`extract links/timeline/all`。 | 项目复盘、关系查询、会议/邮件追踪优先用 GBrain graph/timeline。2026-06-02 已先落 Project_R graph adapter 竖切片：从 GBrain source-of-record `derived/` Markdown/frontmatter 生成 `nodes/edges/events/citation`，正式验收覆盖 `company-wiki`、`project-*` 和受限客户情报数据范围；客户工作区读取 GBrain 已精炼吸收的客户情报数据并由 Project_R 权限控制可见性。管理员图谱、实体候选入口、安全 diff 预览、受控 frontmatter 引用改写、工作区客户画像/项目事件入口、token-bound native graph/timeline/backlinks context、侧栏筛选/节点详情、Timeline 分组折叠/密度切换、小画布、事件详情、大画布 pan/zoom 和安全 source preview 已接入。 | 直接沿用 + Adapter 包装已起步 | Project_R 不再用简单文本 chunk 模拟关系查询；当前客户情报图谱、工作区只读图谱、工作区实体候选审核、别名审核沉淀、实体合并安全 diff 预览、受控 frontmatter 引用改写、token-bound native graph context、侧栏筛选/节点详情、Timeline 分组筛选与折叠/密度切换、侧栏小画布、事件详情、全屏大画布基础 pan/zoom 和安全源文件预览可回归验证，但自动布局优化、native timeline 可视化增强、重复页面自动合并、正文级实体合并和实体页删除仍未完成。 |
| Schema packs | 内置 schema packs，可 detect/suggest/review/apply；支持 agent-authored schema。 | README schema section；`schema_*` operations；`skills/schema-author`。 | 先用默认 `gbrain-base-v2`；后续为公司项目资料设计 Project_R schema pack。 | Adapter 包装 + Skillify 补齐 | 过早自定义 schema 会增加迁移成本；先用默认跑通。 |
| Skills / Resolver | 43 个左右 curated skills，resolver 负责触发和组合。 | `skills/RESOLVER.md`。 | Project_R Agent 功能先映射到 GBrain 原生 skills，业务 UI 只做入口和状态。 | 直接沿用 + Adapter 包装 | Project_R 自己的业务 Skill 与 GBrain skill 需要命名边界，避免重复。 |
| Skillify | 把重复功能补成正式 skill：SKILL.md、代码、测试、resolver、E2E、eval。 | `skills/skillify/SKILL.md`；`src/commands/skillify.ts`。 | 原始文件提炼优先做成 Project_R extractor skill；GBrain Skillify 后续只用于 GBrain 内部后处理能力或作为设计参考。 | Adapter 包装 / 暂缓 | 不用于一次性修答案；不要把 Project_R 原始文件生命周期重新交给 GBrain。 |
| Minions / Jobs | 持久化 job queue、subagents、shell jobs、progress、cancel/retry。 | README Minions；operations `submit_job`、`submit_agent`、`list_jobs`、`get_job_progress`、`cancel_job`、`retry_job`。 | Project_R 管理员后台已接入 jobs 列表、提交、取消、重试和通知；提交白名单仅允许 `sync/embed/lint/import/extract/backlinks/autopilot-cycle`，不开放 `shell`。citation-fixer 走 `submit_agent`，不混入普通 job 白名单；当前已为 Dream Cycle、citation-fixer 和 contradiction probe 分别建立 Project_R-side manifest / worker tick / 轮询或运行结果通知。 | Adapter 包装 | 仍需 GBrain 原生 Postgres worker 长跑验收、Project_R job id 与 GBrain job id 的统一长期映射、批量任务策略和失败回滚。 |
| MCP / HTTP / OAuth / Scope | `gbrain serve --http` 提供 OAuth 2.1、read/write/admin scopes、MCP tools。 | README MCP；`src/commands/serve-http.ts`。 | 第一版已确认由 Project_R 后端 service account adapter 调用 GBrain HTTP/MCP 常驻服务；后续再评估用户级 OAuth/scope。 | Adapter 包装 | 用户级权限不能只依赖 GBrain scope，Project_R 项目权限仍是第一层。CLI 不作为正式业务调用主路径。 |
| 文件存储 | GBrain 有 files/status/verify、raw sidecars、storage tiering 等能力。 | `skills/maintain/SKILL.md` file storage health；`docs/storage-tiering.md`。 | 原始文件仍由 Project_R 管；GBrain 文件能力只作为派生资料/附件/sidecar 辅助。 | Project_R 保留 + 暂不接入 | 避免两套系统同时拥有同一个原始文件生命周期。 |
| 评测 / 搜索质量 | LongMemEval、eval export/replay、cross-modal eval、search benchmark。 | README eval framework；`docs/eval/*`；`skills/maintain/SKILL.md` benchmark。 | 已有第一版 Project_R 管理员质量回归入口：query 回归默认运行，Think 回归需显式 `include_think=true`，用于升级前和配置变更后验收。2026-06-02 已补质量报告存档、趋势和导出：回归报告保留最近 20 份到 `manifests/gbrain-quality-reports.json`，管理员 GBrain 面板展示最近报告的 query/think 通过数、失败用例、preflight 错误和最近 5 次趋势；`GET /admin/knowledge/quality-reports/{id|latest}` 可导出单份 JSON 报告。 | Adapter 包装 | 当前先覆盖公司真实样本的 query/think 回归；后续再接 GBrain eval/benchmark、项目/customer source 回归和升级前后差异分析。 |
| 邮件 / 会议 / 日历 / 语音 recipe | GBrain 有会议、邮件、voice、webhook recipes 和 ingestion skills，可作为 Project_R extractor skill 的参考。 | README integrations；recipes；`docs/integrations/*`；`skills/meeting-ingestion/SKILL.md`；`skills/voice-note-ingest/SKILL.md`。 | 项目会议、邮件、复盘资料由 Project_R extractor skills 负责提炼和归属；GBrain 接收按 source scope 写入的 Markdown。当前已先做音视频同名 transcript 侧车 adapter。 | Project_R 保留 + Adapter 包装 | 自动转录、公司邮件/聊天系统格式需要单独做 Project_R 适配；GBrain 后续负责 sync/query/think/citation/maintain。 |
| 图片 / 跨模态检索 | 支持 image import、多模态 embedding、`search_by_image` operation；OCR 可配置。 | `src/core/import-file.ts`；operations `search_by_image`。 | 后续用于项目图片/截图；第一阶段不作为公司 wiki 主路径。 | 暂不接入 | 截图质量、OCR、隐私和引用定位需要独立验收。 |
| 代码库检索 | 支持 code import、symbol/code edge、code retrieval ops。 | `src/core/import-file.ts` code path；operations code retrieval。 | Project_R 当前不是代码知识库产品，暂缓。 | 暂不接入 | 仅在未来做内部研发知识库时启用。 |

## 第一阶段接入切片

1. 功能盘点和边界确认：本文件作为决策入口。
2. GBrain 运行方式确认：正式业务采用 GBrain HTTP/MCP 常驻服务 + Project_R 后端 service account adapter；CLI 只用于开发期初始化、诊断、人工运维和应急排障。
3. 准备切片已实现：`core/gbrain.py` 读取配置，当前 MVP 初始化 `backend/workspace_data/global/company-wiki/{raw,derived,manifests}` 和 `derived/` 本地 Git；目标架构需迁移到 `_preprocessed/.../{gbrain-ready,runs,manifests}`，并通过 `/health/gbrain` 暴露环境、GBrain 服务健康状态和 source 注册检查。
4. `company-wiki` source 已在本机 GBrain PGLite brain 中注册：当前 MVP 绑定 `backend/workspace_data/global/company-wiki/derived/`；迁移后应绑定 `backend/workspace_data/_preprocessed/company/company-wiki/gbrain-ready/`。
5. 原始资料摄取 worker：扫描公司 raw、项目/客户文件面板当前路径或右键单文件，先输出 `file_kind`、`extraction_complexity`、`extractor_profile` 和 `classifier_reason`，再按文件类型调用 Project_R 独立 preprocessor Skills，过程文件写入 `runs/`，最终 Markdown 写入对应 source 的 `gbrain-ready/`，状态写入 `manifests/`；DeepSeek 负责文字类提炼，MiMo V2.5 负责 PDF、视觉/版式/图片类提炼，音视频先走转写流程。缺能力类型标记 `pending_capability`，完成或失败后通知触发用户；个人工作台附件不进入公司库。
6. 索引同步：调用 GBrain import/sync，状态写回 Project_R 管理员后台。
7. 问答 adapter：Project_R 的知识库问答统一通过 `/query` 调用 GBrain native `think`，前端展示引用、gap、冲突；底层仍保留 `query(..., source_id=company-wiki)` 作为质量回归、diagnostic 和维护工具，不作为普通用户的最终回答层。产品语义上，`/query` 是“查询知识库”Skill 调用指令，不影响普通 chatbot 对日常问题的回答。
8. 纠错闭环：用户反馈错误答案后，Project_R 建立审核项，定位引用和来源，再调用 citation-fixer、maintain、contradiction review 或 Skillify 后的 Project_R 专用修正流程。当前第一段已落地：低分且带 GBrain 引用的回答反馈会生成管理员知识纠错审核项；citation-fixer 已补 `submit_agent` 提交入口、管理员表单和 `backend/scripts/gbrain_agent_preflight.py` 预检；`patches/gbrain/0004-agent-bound-oauth-client-registration.patch` 已补齐 GBrain 侧绑定型 agent OAuth client 注册入口；`0005`/`0006` 已补齐 source scope 与 DeepSeek gateway-loop 执行兼容。真实 client 注册、gateway loop、submit_agent 绑定、PGLite 只读 inline 执行、2026-06-02 真实改写型 smoke、管理员 job 追踪、低分审核项受控触发、单任务回滚和 Project_R worker 轮询均已验收；仍待 GBrain 原生 Postgres worker 长跑或 PGLite inline 管理员执行策略、批量任务费用/权限边界和复杂恢复策略。

本节只描述能力边界和切片顺序；文件进入源文件目录、如何生成 `gbrain-ready/`、GBrain import/sync 的职责、PDF/音视频如何提炼，统一以 `docs/specs/gbrain-ingest-workflow.md` 为准。

## 2026-05-28 本机准备状态

- `reference/gbrain-master` 版本为 `0.42.51.0`；Windows 下普通 `bun install` 会被类 Unix `postinstall` 脚本拦截，本机使用 `bun install --frozen-lockfile --ignore-scripts` 完成依赖检查。
- GBrain 运行目录固定为 `GBRAIN_HOME=backend/workspace_data/global/company-wiki`；GBrain 实际配置和 PGLite 数据库位于 `backend/workspace_data/global/company-wiki/.gbrain/`，仍在 `workspace_data/` 资料根下，不进入主 Git。
- 本机已在 2026-05-29 按 GBrain PGLite 路径切换到本地免费 embedding：`gbrain reinit-pglite --embedding-model ollama:mxbai-embed-large --embedding-dimensions 1024`，当前 schema pack 为 `gbrain-base-v2`。Ollama 已安装并拉取 `mxbai-embed-large`，真实 embedding 已生成。
- 本机 MVP 曾执行 `gbrain sources add company-wiki --path backend/workspace_data/global/company-wiki/derived --name "Project_R Company Wiki" --federated`；迁移后应改为 `_preprocessed/company/company-wiki/gbrain-ready` 路径。
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
- 新增硬性语言规则：PDF 结构化输出必须标记 `language_policy: bilingual_zh_en_aligned`，并在标题、核心结论、关键参数、业务建议、风险边界和待审核问题中保持中英文同义对齐；若模型输出明显不满足双语结构，提炼流程失败，不写入 GBrain-ready Markdown。
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

1. Markdown / txt：最接近 GBrain 的 Markdown/frontmatter 系统记录，优先用于跑通 `source files -> gbrain-ready -> source sync -> query/think -> 引用展示 -> 管理员状态` 主链路。
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

验收重点是证明 `source files -> gbrain-ready -> GBrain source sync -> query/think -> 引用展示 -> 管理员状态` 链路可用。

## 旧 RAG 退役记录

删除旧 RAG 相关代码前置条件：GBrain `company-wiki` source 已注册，`import/sync` 链路可用，`/query` 或等价知识库问答入口已改走 GBrain adapter，并能展示引用和健康状态。当前这些正式路径前置条件已满足，旧主路径已退役。

退役范围：

1. 聊天检索路径：已移除 `api/chat.py` 中对 `RAGEngine`、`WikiRouter`、`_search_rag_sources`、`_search_wiki_sources` 的依赖，改为 GBrain adapter。
2. 旧 API：已替换 `api/rag.py`，当前 `/admin/knowledge/*` 是 GBrain 管理接口。
3. 旧核心：已删除 `core/rag_engine.py` 与 `core/wiki_router.py`。
4. 旧运行数据：不再使用 `backend/vector_store/` 和 `backend/knowledge_base/wiki/` 作为知识库来源。
5. 旧测试：`test_rag_api.py` 和聊天主路径测试已改写为 GBrain；`test_rag_engine_phase10a.py`、`test_wiki_router.py` 已删除。
6. 旧依赖：正式配置项已从 `.env.example` 移除；`requirements.txt` 已移除 `chromadb`、`sentence-transformers`。
7. 审核写入点：审核通过后写入对应 GBrain-ready source repo。管理员公司知识进入 `_preprocessed/company/company-wiki/gbrain-ready/`，项目工作区资料进入当前项目 `gbrain-ready/`，客户资料进入受限客户情报 `gbrain-ready/`；审核队列保留给答案反馈纠错、显式提升公司知识和异常情况。
8. 前端和文档：用户可见主路径已改为 GBrain 知识库状态与来源引用。

删除原则：不做旧索引迁移，不保留 Chroma fallback，不把旧 `knowledge_base/wiki` 当作 GBrain 权威输入。

## 下一批需要继续对齐的问题

1. GBrain `think` 已纳入 Project_R `/query` 的最终回答层：Project_R 已有 guarded adapter、本地上游 `think` source-scope patch，并已完成 `company-wiki` source-scoped OAuth + MCP 服务链路、DeepSeek 综合回答、citations、基础 gap/conflict/warning 前端展示、GBrain Think 审核提交 MVP、质量报告存档/趋势/导出 MVP 和第一条真实服务回归验收。项目 source 已补自动注册/复用 source-scoped Think OAuth client 的代码级能力。下一步需要用新测试项目做真实项目 Think 回归、扩展客户 source 回归和 graph/timeline/maintain 流程入口。
2. 项目级 source 映射：adapter 和项目文件编译第一版已完成稳定 source id、路径、状态展示、manifest、查询 source scope；下一步把现有 `derived/` MVP 路径迁移到 `_preprocessed/project/.../gbrain-ready/`，把录入入口改为当前路径递归确认和右键单文件录入，并用真实项目文件跑通 ingest/gbrain-ready/sync/query/通知。
3. 音视频转写与会议提炼：接入 GBrain voice-note/transcription 路径或 Project_R adapter，并定义口音、多语言、术语纠错和人工抽检流程。
