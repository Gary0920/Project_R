# Project_R 领域术语表

本文档给 Agent 提供 Project_R 的核心领域语言。产品范围、阶段进度和业务 Skill 清单以根目录文档为准：

- `Project_R PRD.md`
- `Project_R 开发流程.md`
- `Project_R 业务工作流清单.md`
- `AGENTS.md`

## 工作姿态 (Work Stance)

Chat 与 Agent 不是会话分类，而是同一会话上的两种**工作姿态**。

- **Chat 姿态**：回答、澄清、起草、解释、引用知识库。
- **Agent 姿态**：执行、调用 Skill、生成文件、检查项目资料、追问字段、展示执行状态。

姿态由全局 `activeModeAtom` 统一管理，不是会话属性，不是标签页属性。
标签页是**中立**的，不记录姿态类型。

## 标签页 (Tab)

标签页是会话或功能面板的打开句柄，属性只包含：
- `id`、`sessionId`、`workspaceId`、`title`

不包含 `type`（chat/agent），不绑定姿态。
历史对话单击默认复用当前标签；只有中键、Ctrl 点击或右键菜单“在新标签页打开”才创建新标签。

## 工作区主页 (Workspace Home)

工作区主页是当前工作区没有打开标签或没有对话时显示的真实工作起点。

- 允许关闭所有标签页。
- 工作区主页包含输入框、最近对话、项目文件入口和项目目录入口。
- 在主页发送首条消息默认创建 Chat 对话；若首条消息触发 Agent、Skill、文件生成或多步骤执行意图，则自动切换到 Agent 姿态。

## 项目目录面板 (Project Directory)

项目目录面板是搜索、加入、打开和新建公司项目工作区的统一入口。

- 入口显示为“项目目录”。
- 公司项目按 `AURA`、`BFI`、`SPECWISE`、`SYNOVA` 品牌分组。
- 新建公司项目时必须选择品牌，再填写项目代号。

## 工作区 / 项目 (Workspace / Project)

工作区是 Project_R 的软件使用容器；在业务上，每个工作区一一对应一个项目，通常以项目代号命名。

- 用户界面可使用“工作区”表达软件操作入口，业务语境使用“项目”表达资料归属。
- 代码内部历史命名继续使用 `workspace`，不代表业务上存在独立于项目的另一类容器。
- 后端创建工作区时同步创建系统管理的项目资料目录。
- Project_R 后端统一资料源根目录为 `workspace_data/`，不额外新增同级 `knowledge_sources/` 目录。
- 全局知识库、公司项目资料和用户私人资料都属于 Project_R 管理的资料源，但按子目录隔离。
- 公司全局知识库源文件位于 `workspace_data/global/company-wiki/`。
- `workspace_data/global/company-wiki/raw/` 存放管理员手工放入的公司全局知识库原始源文件。
- `workspace_data/global/company-wiki/derived/` 存放 GBrain 解析、转换或提炼后回写的可审阅 Markdown，并直接作为 GBrain `company-wiki` source repo。
- `workspace_data/global/company-wiki/derived/` 默认不是人工编辑区；人工修正应优先通过源文件修订、知识审核或专门纠错流程形成可追溯变更。
- Project_R 不为 `company-wiki` 另建一套 GBrain repo 后再同步；`derived/` 就是 GBrain source path。
- `workspace_data/global/company-wiki/derived/` 启用本地 Git 版本记录，仅用于审计、对比和回滚；不默认配置远程仓库，不上传 GitHub，不进入 Project_R 主代码仓库。
- `workspace_data/global/company-wiki/manifests/` 存放摄取状态、错误信息、来源映射和重跑记录。
- 项目文件只能存放在系统管理的项目资料目录内：公司项目位于 `workspace_data/project/{品牌}/{项目代号}`，用户默认工作区位于 `workspace_data/user/{用户名}`。
- 品牌级目录固定为 `AURA`、`BFI`、`SPECWISE`、`SYNOVA`，品牌下一级才是具体业务项目。
- 公司项目资料目录默认包含 `01-合同与报价`、`02-图纸与技术资料`、`03-会议纪要`、`04-变更与签证`、`05-生产与发货`、`06-现场与客诉`、`99-未归档文件`。
- 用户默认工作区资料目录默认包含 `对话文件` 和 `固定文件`。
- 每个用户都有一个默认工作区，显示名为 `{用户名} 的私人空间`，可见且置顶，不可删除、不可重命名、不可归档。
- 默认工作区不属于公司项目，不显示在公司项目目录面板中。
- 项目成员可上传文件；成员只能删除自己上传的文件；管理员可删除所有文件。
- 删除进入回收区，支持恢复与永久删除。
- 项目资料只影响对应项目内的项目对话，不影响其他项目或无项目会话。
- 已加入该项目的其他用户，在项目对话中可使用该项目资料。
- 项目资料不能覆盖公司全局底层规则。

## 系统管理员 (System Administrator)

系统管理员是拥有 Project_R 全局后台管理权限的用户角色。

- 系统管理员用于处理用户管理、全局知识审核、系统健康告警、LLM Key/成本告警和全局配置类事务。
- 系统管理员不等同于某个项目内的工作区管理员。

## 工作区管理员 (Workspace Administrator)

工作区管理员是某个项目资料容器内拥有管理权限的成员角色。

- 工作区管理员用于处理对应项目内的文件管理、成员协作和项目级风险通知。
- 工作区管理员不自动拥有系统后台管理权限。

## 会话临时附件 (Session Attachment)

会话临时附件只服务当前会话，是用户在聊天中临时提供的参考材料。

- 不自动进入项目资料库。
- 可通过附件按钮、剪贴板粘贴或拖拽到对话区添加。
- 默认按用户和会话隔离，存放在用户默认工作区的 `对话文件/{session_id}` 目录。
- 会话超过 3 天未活跃后自动清理；删除会话时同步清理。
- 文本类附件和可提取文本的 PDF 可进入本次对话上下文。
- 图片附件在支持图像输入的 MiMo 模型下会以多模态 content block 投递给模型；DeepSeek 等不支持多模态的模型会阻止发送并提示切换模型。
- 视频、音频、OCR 和不可提取文本的扫描 PDF 仍属于后续能力，当前不会静默当作可解析内容使用。
- 后续可通过“保存到项目资料”以复制方式沉淀到当前项目的 `99-未归档文件`。

## 全局底层规则 (Global Base Prompt)

`backend/prompt_presets/global-base-prompt.md` 是公司级全局底层规则文件。

- 文件可为空，空文件不影响现有行为。
- 有内容时由后端强制注入到 system prompt 最前面。
- 普通用户不可切换、关闭或编辑。
- 优先级高于会话提示词、Agent 模式提示、附件、项目资料、知识库和用户输入。

统一上下文优先级：

1. 全局底层规则
2. 会话选择提示词 / Agent 模式提示
3. 会话临时附件
4. GBrain source 检索结果 / 当前项目资料
5. 用户问题

## 会话提示词 (Session Prompt)

会话提示词是当前会话的 system prompt 选择，不是输入框模板。

- 来源分为 Project_R 内置提示词、公司预设提示词、用户本机自定义提示词。
- Project_R 内置提示词只读；公司预设提示词由后端保存；用户自定义提示词保存在 Electron `userData` JSON，不进 Git、不上传后端。
- 选中提示词后只在输入框上方显示 chip，不改写输入框正文。
- 每个会话独立选择提示词，新会话默认使用 Project_R 内置提示词。

## 文本变换类提示词 (Text Transformation Prompt)

文本变换类提示词用于处理用户已提供的文本本身。

- 典型任务包括改写、润色、翻译、压缩、扩写、格式整理和语气调整。
- 文本变换类提示词不是知识库问答，也不是项目资料分析。
- 选中文本变换类提示词时，系统默认不引入公司知识库、项目资料或外部规范。
- 用户明确使用 `/query` 或明确要求查询公司资料、知识库、项目文件时，才切换为知识库问答。
- `/query` 是 Project_R 软件内“查询知识库”Skill 调用指令；普通 Chat 保持 chatbot 能力，不自动查询 GBrain。
- 文本变换类提示词不得新增用户原文没有的事实、标准号、文件名、分类、建议或结论。

## 模型配置档 (Model Profile)

`model_profile` 是用户可见的模型路由配置档，不是 API Key。

- 后端通过 `LLM_MODEL_PROFILES` 等配置把 profile 映射到 provider、真实模型名、描述文案和私有参数。
- 多个 profile 可以共享同一组 provider Key，例如 DeepSeek Flash / Pro 共享 DeepSeek Key，MiMo V2.5 / V2.5-Pro 共享 MiMo Key。
- 前端模型下拉只显示 `/health/llm` 返回的已配置 profile；未配置 API Key 的模型不显示、不占位。
- 前端不得暴露 API Key、Provider 切换、多 Key 配置或厂商私有参数。

## 思考模式 (Thinking Mode)

输入区“思考”按钮是参数开关，不是模型切换。

- 前端发送 `thinking` 布尔值。
- DeepSeek 由后端生成 `thinking.type` 与 `reasoning_effort`。
- MiMo 由后端生成 `thinking.type`。
- 推理火力大小保留在后端环境变量或 profile 配置中，不作为员工端 Key/Provider 配置暴露。

## 知识库 (Markdown Wiki / GBrain)

Project_R 的知识库产品边界是：GBrain 是知识库内核，Project_R 是公司业务入口、权限审计、原始资料保管、知识审核和可视化工作台。

- `backend/knowledge_base/wiki/` 是当前公司全局知识库的既有 Markdown 资产；这些文件来自 Obsidian 复制导入，属于开发阶段临时资产，不作为 GBrain 接入后的权威知识库。
- 公司知识库可在 GBrain 架构接入后，从重新投喂的 Obsidian 源文件或其他源文件重新摄取生成。
- 旧 Project_R RAG 不做迁移：`knowledge_base/wiki`、Wiki Router、Chroma/vector_store 不作为 GBrain 的回退层或权威输入；由管理员重新投喂源文件生成 `company-wiki`。
- GBrain 负责资料解析转换、导入、索引、graph、hybrid search、综合回答和 gap analysis。
- Project_R 不从零自研全部资料解析转换器，优先沿用 GBrain 的 source、ingestion、content-type processor 或等价解析转换能力。
- Project_R 的知识库、检索、摄取、纠错、维护、Skill 和 Agent 相关能力采用 GBrain-native first 原则：先确认 GBrain 是否已有原生 command、operation、skill、recipe 或 schema 机制，再决定 Project_R 是否只做 adapter 和 UI。
- Project_R 不重复建造 GBrain 已经具备的复杂知识库核心能力；只有 GBrain 缺口明确、且无法通过配置、adapter 或 Skillify 补齐时，才在 Project_R 内新增能力。
- GBrain 生成的派生 Markdown 必须保持可审阅、可备份、可迁移；运行时索引不能成为唯一不可见事实源。
- Project_R 可以作为 GBrain 知识库的显示载体，但不能退化成纯前端壳；身份权限、项目边界、审计、原始文件生命周期和知识审核仍属于 Project_R 的业务责任。
- Project_R 是 GBrain 摄取源文件的管理入口；用户和管理员只需要把源文件放入 Project_R 管理的全局或项目资料位置。
- Project_R 后端统一使用 `workspace_data/` 作为资料源根目录；全局、项目和用户资料分别按 `global/`、`project/`、`user/` 子目录隔离。
- 公司全局知识库源文件由管理员手工放入 `workspace_data/global/company-wiki/raw/`，再由 Project_R 调用 GBrain 摄取到 `company-wiki` source。
- GBrain 为 `company-wiki` 生成的派生 Markdown 回写到 `workspace_data/global/company-wiki/derived/`；该目录直接作为 `company-wiki` 的 GBrain source repo。
- `company-wiki` 的 `derived/` 目录初始化为本地 Git repo；Project_R / GBrain adapter 在成功写入或更新派生 Markdown 后提交本地 commit，并保留 manifest id 或来源文件引用。
- Project_R 在 `workspace_data/global/company-wiki/manifests/` 保留摄取状态、错误信息、来源映射和重跑记录。
- 项目知识源文件来自用户在 Project_R 项目 / 工作区中上传的项目文件，再由 Project_R 调用 GBrain 摄取到对应项目 source。
- GBrain 只读取 Project_R 授权的源文件路径或受控输入；用户不需要直接操作 GBrain 内部目录。
- 在 GBrain 接入 Project_R 前，必须先形成 GBrain 功能盘点矩阵，区分可直接沿用、需要 adapter 包装、需要 Skillify 补齐和暂不接入的能力；当前矩阵文档为 `docs/gbrain-feature-inventory.md`。
- Project_R 使用一个受系统管理的 GBrain brain，并按知识边界拆分多个 source。
- 公司全局知识库映射为 `company-wiki` source。
- GBrain 接入 Project_R 的第一条竖切片只覆盖公司全局知识库 `company-wiki` source。
- 第一条竖切片的验收重点是源文件重新投喂、GBrain 解析索引、Project_R 查询展示引用和管理员查看索引状态。
- 每个公司项目 / 工作区必须映射为独立项目 source，用于该项目资料、会议文件、邮件文件和项目级信息提炼。
- 每个用户私人空间后续可映射为独立用户 source，用于个人固定资料和长期记忆。
- 会话临时附件默认不进入 GBrain source；只有用户明确保存到项目资料或知识库后才进入对应 source。
- 项目 source 中的项目资料、会议、邮件和事件可定期形成项目复盘总结。
- 项目复盘总结是项目经验向公司全局知识库演进的桥梁；它用于从具体项目事实中提炼可复用规则、流程、风险清单、模板建议和培训经验。
- 项目复盘总结进入公司全局知识库前必须经过 Project_R 的知识审核或等价治理流程，不能直接无审核覆盖公司级规则。
- 项目复盘总结沉淀到公司全局知识库时，先生成可沉淀知识候选稿，而不是自动写入公司级规则。
- 可沉淀知识候选稿按公司规则、流程优化、风险清单、模板建议、培训经验和待验证假设等类型标记。
- 审核通过后，候选稿才写入公司全局可审阅 Markdown 知识源并同步进入 `company-wiki` source。
- 当候选稿与既有公司知识冲突时，Project_R 应生成冲突说明或修订建议，而不是自动覆盖旧规则。
- Project_R 调用 GBrain 时按工作姿态分层使用：Chat 普通知识问答优先用 `query` / `search` 取证据片段，再由 Project_R 当前 LLM 统一回答。
- Agent 执行任务、项目复盘和跨文件综合可使用 `think`，以获得综合回答、引用和 gap analysis。
- 需要严格格式输出的业务 Skill 不直接依赖 `think` 的最终自然语言答案，应使用 `query` / `search` 获取结构化证据，再由 Skill runner 按模板或规则输出。
- 管理员知识审核可以使用 `query` / `search` 与 `think` 辅助判断，但审核记录必须保留原始引用链，不能只保存综合结论。
- 第一版由 Project_R 后端统一持有 GBrain 管理连接，并由 Project_R 自己根据登录用户、工作区成员关系和管理员角色决定可查询的 GBrain source。
- 第一版不为每个 Project_R 用户单独维护 GBrain OAuth client；GBrain OAuth source scope 可作为后续更强隔离方案。
- Project_R 的 GBrain adapter 必须默认拒绝跨 source 查询；每次查询必须显式指定允许的 source，并写入审计日志。
- GBrain 在 Project_R 第一版中作为独立知识引擎服务运行，而不是直接揉进 FastAPI 进程。
- Project_R 第一版正式业务采用 GBrain HTTP/MCP 常驻服务 + Project_R 后端 service account adapter；不把 CLI 子进程作为正式业务调用主路径，也不直接依赖 GBrain TypeScript library。
- Project_R 后端通过 GBrain adapter 调用独立服务的 `query` / `search` / `think` / `import` / `sync` / `status` 等能力。
- CLI 只用于开发期初始化、诊断、人工运维和应急排障。
- GBrain 准备切片已实现：`core/gbrain.py` 负责配置读取、目录初始化、`derived/` 本地 Git 初始化、service account token 隐藏、GBrain `/health` 探测、MCP `sources_list` / `sources_status` 解析，以及通过 MCP `query` 显式指定 `source_id=company-wiki` 的检索 adapter；`/health/gbrain` 暴露环境、服务健康状态和 `company-wiki` source 注册检查。`think`、自动 import/sync worker 和前端引用展示仍待后续接入。
- 本机 GBrain 已用 `GBRAIN_HOME=workspace_data/global/company-wiki` 初始化 PGLite brain，`company-wiki` source 已注册到 `workspace_data/global/company-wiki/derived/`，`gbrain serve --http --port 3131 --bind 127.0.0.1` 可返回 service ok；配置 service bearer token 时 `/health/gbrain` 可返回 `registered=true` 和 `path_matches=true`。
- 2026-05-28 真实样本已验证：`raw/` 中 4 个 Markdown、1 个 DOCX、2 个 PDF 曾成功编译为 7 个 `derived/` Markdown；1 个 MP3 因未配置音频转写被 manifest 标记为 skipped。该轮 PDF 编译属于质量验证，不代表 PDF 纯文本抽取被接受为长期入库方案。
- 2026-05-29 已清退两个 PDF 纯文本页面：`company-wiki` 当前为 5 页，manifest 为 `compiled=5`、`skipped=3`，`Glass` / `AS 2047` 查询不再命中，`VMU` / `书面化原则` 查询仍正常。
- 2026-05-29 起，PDF 默认不再走纯文本抽取直接进入 `derived/`；PDF 应先进入待提炼状态，通过模型/视觉辅助结构化提炼为可读、可审核、可引用的 Markdown 后，再导入 GBrain source。
- 当前本机 GBrain 初始化使用 `--no-embedding`，因为 Project_R `.env` 没有 GBrain 可用的 OpenAI / ZeroEntropy / Voyage 等 embedding key；真实样本完整 hybrid/vector query 验收前需要补齐 embedding provider，或先明确 keyword-only 验收范围。
- 开发期可在本机启动 GBrain 服务；交付期可在公司内网服务器运行 GBrain HTTP MCP 或等价服务。
- Project_R 主业务不得直接依赖 GBrain 内部数据库表结构；替换或升级 GBrain 应主要影响 adapter 层。
- 项目文件上传后先进入 Project_R 工作区文件系统并记录元数据，状态为待索引。
- Project_R 后台索引任务调用 GBrain 或 GBrain 兼容解析器，将原始资料转换、提炼为项目级派生 Markdown，再同步到对应项目 GBrain source。
- GBrain 可读取 Project_R 授权交给它处理的原始资料副本或受控输入，并向 Project_R 回写派生 Markdown、来源引用、提取状态和错误信息。
- GBrain 不直接接管 Project_R 原始文件的删除、恢复、权限和审计。
- 上传接口不得因 GBrain 导入、Office/PDF/邮件解析或项目提炼而长时间阻塞。
- 文件索引完成后状态变为已索引；失败时保留原始文件并标记索引失败，供用户或管理员重试。
- GBrain 接入第一阶段的文件类型验证顺序为：Markdown / txt → PDF 结构化提炼 → 会议转写文本 → 录音 → 图片 / 截图 → 邮件导出。该顺序是工程验证顺序，不代表长期业务价值排序。
- 第一阶段 `company-wiki` 验收样本由 Gary 手动放入 `workspace_data/global/company-wiki/raw/`；Agent 不凭空生成测试文档，也不使用合成资料冒充真实业务资料。
- 建议最小验收样本为 3 个 Markdown / txt、2 个 PDF、1 份会议转写文本。
- Project_R 后台的知识审核、管理员入口、权限、审计和文件生命周期仍归 Project_R 管理。

- 旧 Wiki Router / Chroma 主路径已清退：`core/wiki_router.py`、`core/rag_engine.py` 和对应旧测试已删除；`backend/knowledge_base/wiki/` 与 `backend/vector_store/` 不作为 GBrain 权威输入或 fallback。
- GBrain 接入后，新知识库检索、项目资料检索、复盘总结和 Agent 知识调用默认走 GBrain source。
- 旧 Wiki Router / Chroma 不得作为切换期兼容层或回退层恢复。
- 普通聊天不得被“知识库未找到”污染。
- 用户可用 `/query ...` 强制知识库问答；其他资料提炼、项目复盘、知识审核、纠错流程应由独立 Skill 或管理员任务承接。
- GBrain 不需要面向普通用户建设复杂知识库浏览入口；普通用户主要在对话中使用 GBrain 能力。GBrain 管理功能应优先做成管理员可用的实用面板，用于 source 状态、摄取状态、健康检查、重跑、审核和错误处理。

## Skill

Skill 是公司业务工作流的可执行封装。

- 内置 Skill 存放在 `backend/skills/builtin/`。
- 当前端到端样板为 U03 标签打印 Skill。
- Chat 负责发现意图和澄清，Agent 更积极承接执行、补参、生成文件和读取项目上下文。
- 修改 Skill 时同步更新根目录 `Project_R 业务工作流清单.md`。

## 文件生成 (Generated File)

文件生成是由 Chat 或 Skill 触发的受控输出能力。

- 已完成 Word tracer bullet 与 U03 Excel tracer bullet。
- 生成文件必须通过后端权限校验下载。
- 运行时生成物不入 Git，属于本机运行数据。

## 通知事件 (Notification Event)

通知事件是 Project_R 内部发生且需要异步告知用户的业务事实。

- 典型事件包括 Skill 完成、Skill 阻断、项目资料索引完成、权限变更、知识审核待处理和系统健康告警。
- 通知事件本身不等于用户收件箱里的通知。
- 第一版不为通知事件建立独立事件表，可通过同批通知记录上的事件标识进行弱关联。

## 通知记录 (Notification Record)

通知记录是某个具体用户在通知中心看到的一条可读/未读消息。

- 每条通知记录只属于一个接收用户。
- 系统广播不使用 `ALL` 虚拟接收人，而是把同一个通知事件分发为多条通知记录。
- 用户的已读、未读和后续免打扰状态以通知记录为准。
- 通知记录默认不是长期审计证据；清理通知记录不得删除审计日志或原始业务记录。
- 通知中心入口位于侧边栏底部设置图标左侧，第一版使用轻量弹出面板而非右侧常驻工具面板。

## 通知分类 (Notification Category)

通知分类描述通知事件来自哪类业务场景。

- 第一版分类为：系统、任务、项目协同、审批、风险。
- 分类用于通知中心筛选，不表达紧急程度。

## 通知级别 (Notification Severity)

通知级别描述通知记录对接收人的处理紧急程度。

- 第一版级别为：信息、成功、警告、严重。
- 是否强提醒、是否需要用户处理和是否只收纳进通知中心，以通知级别和业务动作共同判断。
- 第一版强提醒只面向新产生的任务结果、任务阻断和严重风险；历史未读和普通协作信息只收纳进通知中心。

## 待办型通知 (Actionable Notification)

待办型通知是需要接收人完成业务动作才能闭环的通知记录。

- 已读只表示用户看过通知，不表示业务已处理。
- 待办状态用于表达业务是否已闭环，第一版状态为：无需处理、待处理、已完成、已忽略。
- 知识审核、人工介入请求、异常审计确认和商业风险告警属于待办型通知。
- 任务完成、系统更新和普通项目资料更新默认不是待办型通知。
- 第一版不提供按分类或按项目关闭通知；关键风险通知不能被普通偏好静音。

## 通知动作 (Notification Action)

通知动作是用户点击通知后由前端按白名单执行的结构化操作。

- 新通知优先使用动作类型和动作参数表达跳转或处理目标。
- 旧通知链接只作为兼容字段，不作为长期主要交互协议。
- 第一版动作类型聚焦打开会话、打开项目、打开 Skill 运行、下载文件和打开管理员审核。

## 通知分发 (Notification Delivery)

通知分发是把一个通知事件转换为一个或多个用户通知记录的过程。

- 普通项目文件变化默认进入工作区动态，不进入全局通知中心。
- 项目资料索引完成、索引失败、权限变更、管理员删除他人文件和批量删除异常可触发通知分发。
- 项目风险类资料更新第一版不自动识别内容，可由后续 Agent 或管理员触发通知。
- 第一版通知触发源聚焦 Skill/文件生成结果、知识审核、工作区权限与索引、系统风险告警。

## 工作区动态 (Workspace Activity)

工作区动态是项目资料容器内普通协作流水的轻量记录。

- 普通上传、新建文件夹和一般文件变更属于工作区动态。
- 工作区动态用于项目文件面板内查看，不默认推送到全局通知中心。

## 广播通知 (Broadcast Notification)

广播通知是同一个通知事件面向一组用户分发后的多条通知记录。

- 接收组可以是全员、管理员、项目成员、Skill 发起人或其他明确用户集合。
- 前端和普通通知查询只处理当前用户自己的通知记录，不读取共享广播对象。

## 客户端更新 (Client Update)

客户端更新是员工桌面端从公司内网后端获取新版本安装包并完成升级的交付流程。

- 更新通知只负责提醒用户存在新版本，不负责直接替换程序文件。
- 安装包由 Project_R 后端在公司内网分发，不默认依赖 GitHub Releases。
- 更新过程必须由 Electron 主进程或安装器执行，不能由 renderer 页面直接覆盖应用文件。
- 客户端更新分为普通更新和强制更新；低于最低支持版本的客户端必须更新后才能继续使用。
- 更新交互先展示版本号与更新日志，再进入下载进度窗口，下载完成后提示用户重启完成安装。
- 更新包下载必须在用户确认后开始，不在登录后自动后台下载。
- 更新失败提示使用公司内部语境，引导用户联系管理员获取最新版安装包。
- 更新可用性按当前客户端版本本地检查，不按用户通知记录判断；通知中心只承载更新提醒入口。
- 第一版使用 `electron-builder` 生成安装包，Project_R 自行实现版本检查、下载安装包、SHA256 校验和启动安装器，不默认采用 `electron-updater` 全套发布机制。
- 版本检查接口可在内网未登录访问；安装包下载需要登录鉴权；更新包发布或登记仅限系统管理员。
- 强制更新允许用户完成登录以取得下载权限，但会在进入主工作台前阻断；用户只能下载并安装或退出软件。
