# GBrain 原始资料导入与提炼流程

状态：v0.2，2026-05-31  
适用范围：Project_R 管理的公司全局知识库、项目资料、会议资料、PDF/音视频/邮件等原始文件进入 GBrain source 的流程。

相关进度：GBrain 功能盘点见 `docs/gbrain-feature-inventory.md`；Project_R 对 GBrain 的适配完成度、未闭环项和下一步顺序见 `docs/gbrain-adaptation-progress.md`。

## 核心结论

Project_R 的 `raw/` 是原始资料保管区；GBrain 的 source 不是直接吃所有原始文件，而是吃经过 Project_R Agent / Skills 转换、提炼后写入正式 `derived/` 路径的 Markdown。是否需要审核由 source scope 决定：管理员后台录入的公司知识视为管理员已审核；项目工作区文件默认只进入项目 source，不进公司库且不需要管理员审核；用户私人空间附件不得进入公司知识库。

2026-05-30 已确认新边界：原始文件提炼功能确认在 Project_R 上实现，而不是交给 GBrain 直接处理。DeepSeek 负责文字类原始资料提炼，MiMo 负责 DeepSeek 不支持或不可靠的视觉/版式/图片类资料提炼，API Key 使用 Project_R 后端 Chat/LLM Provider 配置统一管理。用户只触发录入，不手动选择 API Key；Project_R 后端必须先识别文件类型和提炼复杂度，再自动选择对应 `model_profile` 或待能力补齐状态。

GBrain 的 `import` / `sync` 主要负责把 `derived/` Markdown 变成可检索、可引用的索引数据。它不是 Project_R 的默认高质量资料提炼器。PDF、会议录音、视频、截图、邮件这类复杂资料，必须先经过 Project_R 专用提炼 Skill 生成结构化 Markdown，再导入 GBrain。该长期边界见 `docs/adr/0009-pr-owned-extraction-to-gbrain-markdown.md`；按空间决定审核/入库责任的规则见 `docs/adr/0010-source-scoped-knowledge-ingest-review-policy.md`；自动分类与模型路由规则见 `docs/adr/0011-automatic-extractor-routing-by-file-type.md`。

## 目录分层

公司全局知识库第一阶段目录：

```text
backend/workspace_data/global/company-wiki/
  raw/        # Project_R 保管的原始文件，不直接作为 GBrain 查询内容
  derived/    # 可审阅 Markdown，直接注册为 GBrain company-wiki source
    .pending_review/ # 待审核提炼结果，审核通过前不进入 GBrain 查询面
  manifests/  # 摄取状态、错误、来源映射、重跑记录
```

项目资料目录沿用相同语义，但默认不走公司知识审核队列：

```text
backend/workspace_data/project/{品牌}/{项目代号}/
  raw 或项目文件目录
  derived/
  manifests/
```

项目 source 第一版映射规则：

- `source_id = project-{brand}-{workspace_id}`，例如 `project-bfi-7`。
- `source path = backend/workspace_data/project/{品牌}/{项目代号}/derived/`。
- 项目 source 默认 `--no-federated`，不参与跨项目联合检索。
- Project_R 查询项目资料时必须显式传入项目 `source_id`，并先通过 Project_R 项目成员权限判断。
- 项目文件面板提供“一键录入项目知识库”动作；定义上，“未入库文件”覆盖当前项目内所有有知识价值且尚未成功同步进项目 GBrain source 的资料，包括 Markdown/txt、DOCX、PDF、复杂 PDF、音频/视频、图片/截图、邮件和未来支持的业务附件。第一版不是逐个选择文件，而是录入当前项目所有当前可处理且尚未入库的文件，并在按钮旁显示数量，例如“录入 12 个未入库文件”。目前项目路径已支持复杂 PDF/建筑图纸、MP4 自动转写、长视频分段转写、说话人/术语纠错、图片/截图 MiMo 提炼、EML 邮件线程提炼和 EML 附件递归。点击后只写入当前项目 source，完成或失败后通知点击该动作的用户。
- 项目资料默认不提升到 `company-wiki`，也不进入管理员公司知识审核队列。

用户私人空间规则：

- 私人空间上传附件不得进入 `company-wiki`。
- 第一版只作为会话/私人上下文使用；未来即使增加用户私有 source，也必须与公司和项目 source 隔离。

## 标准流程

```mermaid
flowchart TD
  A["用户/管理员放入原始文件"] --> B["Project_R 保存 raw 与元数据"]
  B --> C["识别文件类型、复杂度和 source scope"]
  C --> R0["自动选择 extractor_profile / model_profile"]
  R0 --> D["结构化提炼流程"]
  D --> E["生成可审阅 Markdown"]
  E --> R{"source scope"}
  R -->|"管理员公司知识"| F["写入 company-wiki/derived/"]
  R -->|"项目工作区一键录入"| FP["写入 project source derived/"]
  R -->|"私人空间"| X["只作私人/会话上下文，不入公司库"]
  FP --> G
  F --> G["写入 manifest 与来源映射"]
  G --> H["本地 Git 记录 derived 变更"]
  H --> M["GBrain import/sync"]
  M --> I["GBrain chunk / embed / index"]
  I --> J["/query 调用 GBrain query"]
  I --> K["Agent/管理员调用 think/maintain/审核流程"]
  K --> L["审核通过后沉淀为公司知识"]
```

## 自动分类与模型路由

Project_R 在调用提炼模型前必须先做资料分类，普通用户不需要也不能手动选择 API Key。前端只展示“一键录入”、处理数量、状态和失败原因；后端根据分类结果选择 `model_profile`，再由 `model_profile` 映射到 DeepSeek、MiMo、转写流程或待能力补齐状态。

分类结果至少写入 manifest：

| 字段 | 含义 |
|---|---|
| `source_scope` | 公司、项目、私人或未来扩展 source，决定能否进入公司库。 |
| `file_kind` | `text`、`markdown`、`docx`、`pdf`、`image`、`audio`、`video`、`email`、`archive`、`unknown`。 |
| `extraction_complexity` | `simple_text`、`complex_layout`、`vision_required`、`transcription_required`、`email_thread_required`、`unsupported`、`unknown`。 |
| `extractor_profile` | `deepseek_text`、`mimo_vision`、`transcription`、`pending_extractor_capability` 等后端路由结果。 |
| `classifier_reason` | 简短说明为什么选择该路线，不包含 API Key 或敏感内容。 |

默认路由：

| 文件条件 | 默认处理 |
|---|---|
| Markdown、TXT、干净 DOCX、可读转写文本、可读邮件正文 | DeepSeek 文字提炼。 |
| 普通 PDF：可复制文本、阅读顺序正常、无关键表格/图纸/扫描内容 | 抽文本作为证据，再用 DeepSeek 结构化提炼。 |
| 复杂 PDF：扫描件、多栏、表格/表单、图纸/规格页、抽文本碎片化、关键信息在版式或图片中 | MiMo 视觉/版式辅助提炼。 |
| 图片、截图、表格图片、现场照片、图纸截图 | 项目 source 默认走 MiMo 视觉提炼，生成结构化 Markdown；后续补区域级引用定位和 OCR 回归。 |
| 音频/视频且无 transcript | 项目 source 默认先用本地 ffmpeg 抽音频，再调用 MiMo 自动转写；长媒体按分段处理；转写后再用 DeepSeek 做说话人/术语纠错和会议/知识提炼。 |
| 视频画面也承载知识 | 第一版先做音频转写；如画面本身承载知识，后续需要补 MiMo 关键帧视觉提炼，完成前应明确标记待能力补齐或待人工处理。 |
| 邮件线程或邮箱导出 | 邮件解析器 + DeepSeek 文字提炼；附件保存到 `<邮件名>.attachments/` 后递归重新分类，已支持图片附件进入 MiMo 提炼。 |
| 属于知识目标范围但 extractor 未完成 | 标记 `pending_extractor_capability`，不误报 indexed。 |

复杂 PDF 不只按文件名判断，而按诊断结果和明确图纸线索共同判断：可选文本比例、每页抽取字符数、页数、表格/多栏迹象、图片/扫描页比例、是否存在 PDF 同名 PNG 侧车、纯文本抽取后的阅读顺序是否可用等。明显建筑图纸/总平/立面/剖面/楼层/Rev 图纸包命名，即使存在可复制文本，也默认走 MiMo/视觉待处理路线，避免把碎片化图纸文字误当成可读知识。

## 各区域职责

| 区域 | 职责 | 不做什么 |
|---|---|---|
| `raw/` | 保存原始 PDF、DOCX、音视频、Markdown、邮件、截图等；保留审计和回溯能力。 | 不直接作为普通 `/query` 的主检索内容。 |
| `derived/` | 保存可读、可引用的 Markdown；作为 GBrain source repo。 | 不默认手工乱改，不存不可读的纯抽取垃圾文本；项目 `derived/` 不同步到公司库。 |
| `manifests/` | 保存每个原始文件的状态、错误、hash、目标 Markdown、重跑记录。 | 不作为知识正文。 |
| GBrain DB / index | 保存由 `derived/` 派生出的页面、chunks、embedding、graph、tags。 | 不作为唯一事实源，不直接接管 Project_R 原始文件生命周期。 |

## 审核和责任规则

| 来源 | 默认目标 | 是否需要审核 | 责任人 |
|---|---|---|---|
| 管理员后台录入公司知识 | `company-wiki` source | 不需要额外审核；管理员自行检查 | 操作管理员 |
| 用户私人空间附件 | 不进入公司知识库 | 不进入公司审核流 | 上传用户 |
| 项目工作区附件 | 当前项目 source | 不需要管理员审核；用户点击一键录入当前项目所有未入库文件后生效 | 点击录入的项目用户 |
| 答案低分反馈、纠错、显式提升公司知识 | `company-wiki` 候选 | 需要管理员处理 | 管理员 |

## GBrain 在哪里参与

GBrain 参与分为四层。

### 1. Source 管理

GBrain source 是知识边界。第一阶段：

```text
source_id = company-wiki
source path = backend/workspace_data/global/company-wiki/derived/
```

Project_R 已把每个项目工作区映射为独立项目 source，source id 使用 `project-{brand}-{workspace_id}`。

### 2. 导入与索引

当 `derived/` 里已有合格 Markdown 后，Project_R 调用 GBrain：

- `import <derived> --source-id company-wiki`
- 或后续使用 `sync --source company-wiki`

这一步做的是：

- 读取 Markdown/frontmatter
- 生成页面记录
- 切 chunk
- 生成 embedding，前提是已配置 embedding provider
- 建立 tags、links、timeline 等派生索引

这一步不负责把糟糕 PDF 抽取文本变成好知识。

### 3. 提炼与维护

原始文件提炼归 Project_R Agent / Skills 负责。Project_R 可以参考 GBrain 的 skills、recipes、processor 思路设计自己的提炼技能，但生产链路中由 Project_R 选择模型、调用 API、写入 manifest、生成 `pending_review` 或正式 Markdown。

GBrain 主要在 Markdown 已经存在后参与维护和知识演进，例如：

- `think` 进行综合回答、gap analysis
- `extract links/timeline/all` 提取关系和时间线
- `maintain` / `doctor` / `dream` 做健康检查、矛盾发现、维护建议
- citation-fixer、contradiction probe、graph/timeline、schema、jobs 等后处理能力

Project_R 的原则改为：原始资料提炼优先做成 Project_R extractor skill；GBrain-native first 只保留在 GBrain 擅长的后 Markdown 阶段，例如 source、sync、query、think、citation、graph、schema、maintain 和 jobs。

### 4. 查询与综合

普通用户主要通过对话使用 GBrain：

- `/query ...`：Project_R 的“查询知识库”Skill 调用指令，调用 GBrain `query`，必须显式传入允许的 `source_id`；当前由 GBrain query 返回引用片段，Project_R 当前聊天模型组织最终回答和引用卡片。
- `/query --think ...` 或 `/think ...`：显式试用 GBrain `think` 综合回答。该入口已接入 adapter、OAuth token 获取和来源面板归一化；2026-05-30 已用 `company-wiki` source-scoped OAuth client 完成真实 MCP `think` 调用，确认 token-bound source scope 生效，并通过 `deepseek:deepseek-chat` 产出带 citation 的综合回答；`backend/scripts/gbrain_think_regression.py` 可重复验证该链路。默认仍关闭，因为项目 source 的 think scope、更多问题质量回归和 gap/conflict 前端展示尚未闭环。
- 普通 Chat：不自动查 GBrain，仍保留 chatbot 能力。
- Agent / 管理员任务：可使用 `think`、维护、审核、纠错等流程型能力。

## 文件类型处理规则

| 文件类型 | 当前策略 | 进入 GBrain 的内容 |
|---|---|---|
| Markdown / txt | 可直接作为第一批主链路。 | 保留 frontmatter，补 Project_R provenance 后进入 `derived/`。 |
| DOCX 会议文字 | Project_R 用 DeepSeek 做会议结构化提炼。 | 会议结论、行动项、风险和待确认事项形成 Markdown，按 source scope 进入公司或项目 `derived/`。 |
| PDF | Project_R 不再默认纯文本抽取入库；复杂 PDF/建筑图纸在项目 source 路径默认走 MiMo 视觉辅助结构化提炼。 | 通过 MiMo/视觉/OCR/章节解析生成可读 Markdown 后再进入 `derived/`。 |
| 录音 / 视频 | Project_R 先完成转写，再用 DeepSeek/MiMo 进行会议提炼；项目 MP4 已支持无 transcript 自动转写。 | transcript 侧车或 `.auto.transcript.md` 作为忠实转录层保留；`meeting_structured_extract` 按 source scope 进入公司或项目 `derived/`。 |
| 图片 / 截图 | Project_R 项目路径已用 MiMo/OCR 做视觉理解 MVP。 | 生成结构化摘要、证据、字段/流程和待确认问题后进入项目 `derived/`；后续补区域级引用位置。 |
| 邮件 | Project_R 按线程和项目提炼；项目 `.eml` 已支持解析 + DeepSeek 提炼，并递归处理附件。 | 邮件正文、附件名、决策和行动项整理成 Markdown 后进入项目 source；附件重新分类后各自生成 Markdown。 |

## 语言规则

所有由 Project_R / GBrain adapter / GBrain skill / Skillify 流程生成的提炼型 Markdown，都必须执行 `bilingual_zh_en_aligned` 语言规则：

- 无论原始资料是中文、英文还是中英混合，最终可检索知识页必须中英文并存。
- 中文与 English 必须表达同一事实；英文不得新增中文没有的信息，中文不得省略英文信息。
- 标题、核心结论、关键参数、业务建议、风险边界和待审核问题都需要中英对齐。
- 如果某个信息无法可靠翻译或无法确认，不能单语输出为事实；必须进入“待审核问题 / Review Questions”。
- 原始 source record 可保留原语言；但任何“提炼后进入 GBrain 查询”的知识页必须满足本规则。

## PDF 结构化提炼要求

PDF 进入 `derived/` 前，至少应输出：

- 原始文件名、hash、页码范围
- 文档类型：合同、标准、报价、技术资料、图纸说明等
- 章节/条款结构
- 关键要求、参数、限制条件
- 表格的结构化 Markdown 表达
- 对业务有用的风险点和适用条件
- 不确定或无法识别区域
- 审核状态
- 中英文对齐表达，frontmatter/manifest 标记 `language_policy: bilingual_zh_en_aligned`

纯 `pypdf.extract_text()` 只能作为诊断或中间材料，不能作为默认知识正文。

## 音视频会议提炼要求

音视频进入 GBrain 前分两层：

1. 忠实转录层：保留时间戳、说话人、原文、中英混合、听不清标记、疑似错词。
2. 知识提炼层：会议主题、背景、决策、行动项、风险、待确认事项、项目事件、可沉淀公司知识候选。

默认进入 GBrain 查询的是第二层。第一层保留在 Project_R 文件系统和 manifest 中，供管理员或 Agent 回溯。

当前已实现的 MVP：

- MP3/MP4/MOV/MKV/WEBM 若存在同名 transcript 侧车文件，Project_R 会生成会议结构化 Markdown；项目一键录入路径直接进入当前项目 source，不走管理员审核，公司知识路径按管理员录入/审核规则处理。
- 项目 source 无 transcript 的 MP4 会优先用本地 ffmpeg 抽取音轨，再调用 MiMo 音频理解生成 `.auto.transcript.md`；长媒体默认按 300 秒分段，避免一次请求过长导致截断；随后用 DeepSeek 做说话人映射和术语纠错，再复用会议结构化提炼流程。若音轨抽取失败，才尝试 MiMo 视频输入。
- 支持 `<媒体名>.transcript.md/.txt/.vtt/.srt/.json`、`<媒体名>.zh-CN.transcript.*`、`<媒体名>.zh.transcript.*`、`<媒体名>.en.transcript.*`、直接 `.vtt/.srt`，以及同名目录 `transcript.md/txt/vtt/srt`。
- 输出包含会议主题、决策候选、行动项候选、风险/待确认事项、可沉淀公司知识候选、时间戳摘录和原文转写，并标记 `language_policy: bilingual_zh_en_aligned`。
- 无法转写、分段失败或超过当前模型能力的音视频不会进入 GBrain 查询面，只记录 `pending_meeting_transcription` / `pending_transcription`，等待人工补 transcript 或后续重试。
- 说话人/术语纠错和长视频分段已完成项目 MVP，但置信度、绝对时间戳回链、专业 diarization、人工抽检和公司 source 会议直入规则仍未完成。

质量控制要求：

- 使用公司术语表：人名、客户名、品牌、项目代号、产品词、标准号、中英文常见说法。
- 支持中英混合，不强行翻译为单一语言。
- 低置信内容标记为 `[听不清]` 或 `[疑似：...]`，不得让模型擅自补事实。
- 关键决策和行动项必须回链到时间戳。
- 重要会议进入公司知识库时由管理员录入或触发，视为管理员已自行检查；非管理员产生的会议沉淀若要提升为公司知识，必须走显式提升和审核。

## 附件递归测试方法

附件递归不是前端文件预览问题，而是后端 ingest 能否发现“文件里的文件”，再把抽出来的附件按原规则重新分类和提炼。

当前 `.eml` 测试步骤：

1. 在项目目录放一个带附件的邮件，例如 `99-未归档文件/RE-   Lucerna - Apt. Type 5 Window.eml`。
2. 点击项目文件面板“一键录入项目知识库”，或调用 `POST /workspaces/{workspace_id}/knowledge/ingest`。
3. 后端解析 `.eml` 后，应在同目录生成 `<邮件名>.attachments/`，例如 `99-未归档文件/RE-   Lucerna - Apt. Type 5 Window.attachments/`。
4. 该目录下的附件会在同一次 ingest 的后续扫描轮次中重新进入 classifier。图片附件应显示为 `file_kind=image`、`extractor_profile=mimo_vision`，并生成对应 `derived/unfiled/<邮件名>.attachments/<附件名>.md`。
5. `manifests/project-source-ingest-manifest.json` 里，原 `.eml` 记录应包含 `email_extracted_attachment_files`；每个附件也应有独立 manifest item，最终状态为 `compiled` 或明确失败/待能力补齐。

2026-05-31 真实验收：`GBrain验收项目-001` 的 Lucerna 邮件抽出 4 个 PNG 附件，4 个附件均被递归编译为项目 Markdown；项目 manifest 为 `total=11, compiled=11, pending_extractor_capability=0, pending_transcription=0, failed=0`。

## Manifest 状态建议

建议 manifest 对每个源文件使用以下状态：

| 状态 | 含义 |
|---|---|
| `pending` | 已保存原始文件，尚未处理。 |
| `compiled` | 已生成可导入 Markdown。 |
| `pending_structured_extraction` | 需要模型/视觉/专用流程提炼，尚未生成合格 Markdown。 |
| `pending_transcription` | 音视频文件已保存，但缺少可用转写文本，或自动转写失败、超出当前体积/时长能力。 |
| `pending_extractor_capability` | 文件属于知识库目标范围，但对应 Project_R extractor skill 尚未实现。 |
| `pending_review` | 已生成 Markdown，但需要管理员审核。 |
| `indexed` | 已导入 GBrain source。 |
| `skipped` | 当前类型或条件下明确跳过。 |
| `failed` | 处理失败，可重试或人工介入。 |

## 管理员面板需要展示

GBrain 不需要为普通用户做复杂知识库浏览入口。管理员需要一个实用面板：

- source 列表和健康状态
- raw 文件数量、类型、大小
- manifest 状态统计
- 待结构化提炼文件
- 待审核 Markdown（仅用于答案纠错、显式提升公司知识和异常情况）
- 导入/同步/embedding 状态
- 最近失败原因和重跑按钮
- GBrain health / doctor / maintain 摘要
- GBrain jobs 最近状态、失败原因、取消/重试入口
- contradiction 最近探针结果和后续审核入口
- 答案低分反馈产生的知识纠错审核候选
- 查询/Think 质量回归入口，仅用于管理员验收和升级前检查

## 当前实现状态

- `company-wiki` source 已注册到 `backend/workspace_data/global/company-wiki/derived/`。
- `core/gbrain.py` 已提供 GBrain health/source/query/sync/doctor/status adapter，并支持后端启动/重启 GBrain HTTP 服务。
- 2026-05-30 已接入 GBrain 维护任务第一版：`core/gbrain.py` 包装 `run_onboard(mode=check)`、`list_jobs`、`submit_job`、`get_job`、`get_job_progress`、`cancel_job`、`retry_job`、`find_contradictions`；管理员后台新增“GBrain 维护”页，可看 jobs/contradictions/maintain check，并提交、取消、重试白名单维护任务，操作写审计和通知中心。citation-fixer 已确认是 GBrain agent skill，不是普通 maintenance job，后端已补 `submit_agent` / `submit_citation_fixer` 入口和 `POST /admin/knowledge/gbrain/citation-fixer`，前端管理员 GBrain 维护区已补提交表单。
- 2026-05-30 已接入答案反馈到知识纠错审核 MVP：用户对带 GBrain 引用来源的回答打低分时，Project_R 会把反馈、原问题、原回答摘录和引用来源写成 `gbrain_answer_correction:*` 知识审核候选，并通知管理员；审核通过后沿用现有 `derived/reviews/知识审核沉淀.md` 与 GBrain sync 路径。citation-fixer 已配置本机真实 agent-bound OAuth client，并通过 `backend/scripts/gbrain_agent_submit_smoke.py` 冒烟验证 GBrain 接受 `submit_agent` 工具/source/slug/budget 绑定；随后通过 `backend/scripts/gbrain_agent_inline_execution_smoke.py` 验证 PGLite 下只读 subagent 可在 `company-wiki` source 内执行 `search/get_page`，管理员维护状态可显示 inline execution 已验证。真实 citation-fixer 改写型执行仍需审核保护的测试页或 Postgres worker 验收。预检脚本见 `backend/scripts/gbrain_agent_preflight.py`，注册和运行边界见 `docs/gbrain-agent-citation-fixer-runbook.md`；本地 GBrain 注册与执行兼容能力由 `patches/gbrain/0004-agent-bound-oauth-client-registration.patch`、`patches/gbrain/0005-subagent-tool-source-scope.patch`、`patches/gbrain/0006-chat-tool-json-schema-wrapper.patch` 提供。
- `/health/gbrain` 已读取本地 `.gbrain/config.json` 并暴露非敏感 embedding 状态；当前本机已配置 `ollama:mxbai-embed-large / 1024`，Ollama `mxbai-embed-large` 已安装，返回 `semantic_search_ready=true`。
- `core/knowledge_sources.py` 已修正 GBrain `chunk_text` 字段归一化；中文 `/query` 会同时跑受控英文业务检索词并按分数合并结果，用于提升中英双语知识库中标准/条款类问题命中。
- `core/gbrain_ingest.py` 已提供第一版 raw 扫描和 Markdown/DOCX 编译；管理员后台“导入 raw 并同步”会写 manifest 并调用 GBrain `sync_brain`。
- PDF 结构化提炼 MVP 已接入：默认仍不走纯文本直入库；显式启用 `GBRAIN_PDF_STRUCTURED_EXTRACTION_ENABLED=true` 或管理员点击“含 PDF 提炼”后，`core/pdf_structured_extraction.py` 会用 `pypdf` 读取全文文本作为中间材料，并用 MiMo 视觉模型读取 PDF 同名 PNG 侧车文件夹中的关键页图，生成 `pending_review` + `bilingual_zh_en_aligned` Markdown 到 `derived/.pending_review/standards/`。管理员审核通过后，文件才会提升到正式 `derived/standards/` 并触发 GBrain sync。
- PDF 同名 PNG 文件夹视为视觉侧车资料，不作为独立 raw 文件扫描；当前支持 `GBRAIN_PDF_EXTRACTOR_VISION_PAGES=auto` 自动选择封面、目录、章节分布页、表格/图示/数字密集页，并把实际视觉页码写入 frontmatter 与 manifest。
- 2026-05-29 已用真实样本完成一次 MiMo V2.5 视觉辅助提炼：`AS 1288` 全 153 页文本 + 8 页图，`AS 2047` 全 73 页文本 + 8 页图；两份输出按默认流程先生成 `pdf_structured_mvp_pending_review`，随后在本次验证中标记为 `review_status: approved` 并同步到 GBrain 查询面。
- 音视频会议 transcript 侧车与项目 MP4 自动转写 MVP 已接入：MP3/MP4/MOV/MKV/WEBM 有同名 transcript 时生成 `meeting_structured_extract`；项目一键录入路径直接写入项目 `derived/meetings/`，公司知识路径仍按管理员公司知识规则处理；项目 MP4 无 transcript 时会用本地 ffmpeg 抽音频并调用 MiMo 自动转写，长媒体默认 300 秒分段，生成 `.auto.transcript.md` 后用 DeepSeek 做说话人/术语纠错再提炼。置信度、绝对时间戳回链、专业 diarization 和真实音视频质量回归仍待完成。
- 正式 `/query` 和管理员知识刷新路径已改走 GBrain adapter，不再调用旧 Wiki Router / Chroma / vector_store fallback；旧 `core/wiki_router.py`、`core/rag_engine.py`、旧测试和旧 Chroma 依赖已删除。
- 2026-05-29 已切换到本地免费 embedding：Ollama + `mxbai-embed-large`。为适配该模型较短上下文，本地 `reference/gbrain-master` 的 Ollama recipe 增加 `dims_options=[384,768,1024]`、保守 batch cap，并将 Markdown chunk hard cap 收紧到 400 字符；2026-05-30 PGLite 重建并重新 sync 后，最新 GBrain sync 为 `page_count=7`、`chunks_total=207`、`chunks_unembedded=0`，已生成真实 1024 维向量。
- 2026-05-30 已确认 GBrain 上游源码维护原则：Project_R 不再无记录地直接修改 `reference/gbrain-master`。上述 Ollama recipe、Markdown chunk hard cap、think source scope、agent-bound OAuth client 注册、subagent source scope、AI SDK v6 tool schema/message 兼容均属于当前临时本地 patch，已记录到 `patches/gbrain/`；后续优先通过 GBrain 配置、Project_R adapter、`derived/` 结构优化或向 GBrain 上游提 PR 解决，只有绕不过去才维护 patch 或 fork。
- 2026-05-30 已建立 GBrain 查询质量回归集第一版：`backend/tests/fixtures/gbrain_query_regression_cases.json` 固定真实业务问题和期望来源，`backend/tests/test_gbrain_query_regression.py` 覆盖离线排序逻辑，`backend/scripts/gbrain_query_regression.py` 可对本机 GBrain service + Ollama embedding 跑真实回归。
- 2026-05-30 管理员后台已接入质量回归入口：`POST /admin/knowledge/regression` 默认运行 query 回归，`include_think=true` 时额外运行 Think 回归；前端设置页管理员区可触发“查询回归”和“Think 回归”，展示通过数和失败原因。
- 2026-05-30 已完成项目级 source adapter 第一版：`core/gbrain.py` 可根据 Project_R 项目工作区生成稳定 `project-{brand}-{workspace_id}` source id、计算 `derived/` 路径、返回 registration plan/status，并在服务凭据可用时注册/同步项目 source；`core/knowledge_sources.py` 对项目查询显式传入项目 source id；管理员知识状态返回 `project_sources`。
- 2026-05-31 已完成项目资料一键录入补齐版并通过真实样本增量验收：`core/gbrain_project_ingest.py` 扫描项目工作区文件目录，排除 `derived/`、`manifests/`、`.trash/`、`.git/` 和 PDF 图片侧车目录；将 Markdown/txt、DOCX、普通 PDF、复杂 PDF/图纸、图片/截图、MP4 自动/长视频分段转写、EML 邮件线程和 EML 附件递归编译到项目 `derived/`。`POST /workspaces/{id}/knowledge/ingest` 已接入项目编译、source 注册、sync、通知和 `rag_status` 更新；`POST /workspaces/{id}/knowledge/ingest/async` 已接入后台 job 队列和前端轮询；项目资料直接进入当前项目 source，不进公司库、不走管理员审核。真实样本 `backend/workspace_data/project/BFI/GBrain验收项目-001/` 验收结果为 `total=11, compiled=11, pending_extractor_capability=0, pending_transcription=0, failed=0`。
- 2026-05-30 已完成 GBrain `think` guarded adapter 第一版并补齐上游 source-scope patch：`core/gbrain.py` 可通过 source-scoped OAuth client_credentials token 调用 MCP `think`，`api/chat.py` 支持 `/query --think ...` 与 `/think ...`，`core/knowledge_sources.py` 会把 citations、gaps、conflicts、warnings 归一化为聊天来源面板可显示的来源项。`patches/gbrain/0003-think-source-scope-gather-and-takes.patch` 已让 `runGather()` 把 `sourceId/allowedSources` 传入 `hybridSearch`、takes keyword/vector 和 graph traversal，并补齐 PGLite/Postgres takes SQL 的 `pages.source_id` 过滤；真实 `company-wiki` source-scoped OAuth + MCP `think` 调用已验证 `status=ok` 和 token-bound source scope，配置 `deepseek:deepseek-chat` 后可返回无 warning、带 citation 的综合回答。`backend/tests/fixtures/gbrain_think_regression_cases.json`、`backend/scripts/gbrain_think_regression.py` 和 `backend/tests/test_gbrain_think_regression.py` 已固定第一条可重复验收。正式默认回答层仍保持关闭，等待项目 source scope、扩展质量回归和前端 gap/conflict 展示验收。
