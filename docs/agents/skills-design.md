# Project_R Skills 设计规范

- **格式来源**：参考 Proma Skill 格式（与 Claude Agent SDK 兼容）
- **配套文档**：`docs/product/Project_R PRD.md`、`docs/milestones/Project_R 开发流程.md`、`docs/product/Project_R 业务工作流清单.md`

---

## 一、Skill 是什么

在 Project_R 语境下，**Skill = 一个公司业务工作流的可执行封装**。

每个 Skill 把一段公司流程（例如"中标通知书流程"、"项目交底生成"、"合同审核"）变成可以被用户显式选择，并在长期目标中可被 AI 自动识别、自动收集输入、自动执行、自动输出的能力单元。

---

## 二、三层 Skill 模型

| 层级 | 存放位置 | 来源 | 可见范围 | 是否可改 |
|---|---|---|---|---|
| **官方 Skills** | `backend/skills/builtin/` | 随软件代码分发 | 全员可用 | 不可修改 |
| **企业 Skills** | `backend/skills/enterprise/` | 管理员通过后台上传 | 全员可用 | 仅管理员可改 |
| **个人 Skills** | （暂不开放） | — | — | — |

不开放个人 Skill 是为了避免知识与流程的碎片化，所有业务能力由公司统一治理。当前已完成 U03 无模板输出 tracer bullet；正式模板套用、端到端 UI 验收和更多业务 Skill 继续按根目录开发流程推进。

---

## 三、目录结构

每个 Skill 是一个独立目录：

```
backend/skills/
├── builtin/
│   └── tender-notice/                # 例：中标通知书流程
│       ├── SKILL.md                  # 必需：元数据 + 触发 + 步骤
│       ├── prompt.md                 # 可选：长 prompt 模板
│       ├── template-reference.md     # 可选：使用的文件模板说明
│       └── examples/                 # 可选：输入输出示例
│           ├── input-sample.md
│           └── output-sample.md
│
├── enterprise/
│   └── <某个企业 skill>/
│
└── preprocessors/
    ├── README.md
    ├── markdown-source-preprocess/
    ├── pdf-structured-preprocess/
    ├── drawing-pdf-vision-preprocess/
    ├── image-screenshot-preprocess/
    ├── meeting-transcript-preprocess/
    ├── audio-video-transcription-preprocess/
    ├── email-thread-preprocess/
    ├── spreadsheet-preprocess/
    ├── archive-preprocess/
    └── customer-intelligence-source-preprocess/
```

`preprocessors/` 下的 Skill 不是普通业务流程 Skill，而是资料源文件预处理能力。它们负责把不同文件类型或业务语义的源文件转成 GBrain 友好 Markdown，最终写入 `_preprocessed/.../gbrain-ready/`。每个主要文件类型必须独立成 Skill 或脚本，不能做成一个不可审查的万能 ingest Skill。

---

## 四、SKILL.md 标准格式

每个 SKILL.md 由 frontmatter + 正文组成。

### 4.1 Frontmatter 字段

```yaml
---
name: tender-notice
display_name: 中标通知书流程
description: 项目中标后，自动汇总项目信息生成《项目材料采购信息总览》并推送钉钉
category: 项目启动
priority: high
trigger:
  - 走中标通知书流程
  - 项目中标了，帮我汇总采购信息
  - 提交采购信息总览
inputs:
  - name: project_code
    type: string
    label: 项目编号
    required: true
  - name: tender_files
    type: file_list
    label: 中标通知 / 合同 / 招标文件
    required: true
    accept: [pdf, docx, md]
outputs:
  - type: file
    format: docx
    template: templates/word/项目材料采购信息总览.docx
  - type: dingtalk_push
    target: 项目与采购的沟通群
    mention: 采购经理
references:
  - rules/中标后2周内提交采购信息.md
  - rules/项目规则总览.md
---
```

### 4.2 字段说明

| 字段 | 含义 | 是否必填 |
|---|---|---|
| `name` | Skill 内部标识符（kebab-case） | 必填 |
| `display_name` | 用户可见的名称 | 必填 |
| `description` | 一句话描述（用于 Skill 面板展示，并为后续意图识别匹配保留） | 必填 |
| `category` | 业务分类，对应业务工作流清单中的分类 | 必填 |
| `priority` | high / medium / low | 必填 |
| `trigger` | 触发该 Skill 的自然语言示例（多个，当前用于候选匹配/测试，后续恢复自动意图识别） | 必填 |
| `inputs` | Skill 执行所需输入项 | 必填 |
| `outputs` | Skill 输出形式 | 必填 |
| `references` | 关联的知识库条目（自动检索） | 可选 |

### 4.3 正文结构

```markdown
# 中标通知书流程

## 目的
说明此 Skill 解决的业务问题。

## 触发条件
更详细的触发判定规则。

## 输入收集步骤
1. 询问用户项目编号（如未提供）
2. 让用户上传中标通知 / 合同 / 招标文件
3. 确认信息完整后进入处理阶段

## 处理步骤
1. 从上传文件中提取：地区、地址、位置、使用系统、工程量、初步工期
2. 调用 RAG 检索 [[来源-中标后2周内提交采购信息]] 获取最新规则
3. 套用模板填入字段生成 docx
4. 让用户确认信息无误
5. 推送钉钉群（@采购经理）

## 输出形式
- 主输出：`项目材料采购信息总览_<项目编号>.docx`
- 副输出：钉钉群消息

## 错误处理
- 信息提取失败：让用户手动补充
- 模板缺失：返回"未找到模板，请联系管理员"
- 钉钉推送失败：记录错误日志，不影响文件生成
```

---

## 五、输入类型支持

| `inputs.type` | 含义 | 收集方式 |
|---|---|---|
| `string` | 短文本 | 对话中询问 |
| `text` | 长文本 | 对话中粘贴 |
| `number` | 数字 | 对话中询问 |
| `date` | 日期 | 对话中询问，支持自然语言（"明天"、"下周三"）|
| `file` | 单个文件 | 触发上传卡片 |
| `file_list` | 多个文件 | 触发上传卡片 |
| `select` | 单选枚举 | 显示选项卡片 |
| `multi_select` | 多选枚举 | 显示选项卡片 |

---

## 六、输出类型支持

| `outputs.type` | 含义 |
|---|---|
| `chat_text` | 直接以聊天气泡返回文本 / Markdown |
| `file` | 生成成品文件，前端弹下载卡片 |
| `dingtalk_push` | 推送到钉钉群（需"远程连接"已配置） |
| `knowledge_review` | 写入知识审核队列等待管理员审批 |

一个 Skill 可以有多个 output，按顺序执行。

### 6.1 输出保存边界

- 个人工作台中的轻量业务 Skill / Agent 输出默认只作为本轮结果展示，可复制内容或下载到本地；不提供保存到项目/客户资料的跨工作区动作。
- 项目/客户工作区中的业务 Skill / Agent 输出也必须先作为本轮结果展示；只有用户确认保存后，才写入当前工作区文件面板。
- 工作区 Skill 输出保存位置默认是当前工作区 `99-未归档文件`，并按当前工作区权限、审计、回收站和后续入库候选规则治理。
- 保存到工作区文件面板不等于自动入库 GBrain；GBrain 入库仍需要显式入库动作或另行确认的自动规则。
- 保存后的工作区 Skill / Agent 输出如果属于当前预处理 Skill 支持的文件类型，可进入该工作区待录入候选；个人工作台输出不进入待录入候选。

### 6.2 预处理 Skill 输出模板

预处理 Skill 的输出模板服从 GBrain 吸收质量，而不是 Project_R 自己的展示偏好。设计模板前必须先检查 GBrain schema pack、enrich skill、entity detection、timeline、graph、citation、source sync 和相关 recipe。

所有预处理 Skill 输出至少包含：

```markdown
---
source_scope: project | customer | company
source_file: 原始文件相对路径
source_file_sha256: ...
source_file_type: pdf | image | email | transcript | spreadsheet | ...
preprocess_skill: xxx
preprocess_version: 1
preprocess_status: succeeded | partial | failed | pending_capability
model_profile: deepseek_text | mimo_v2_5_vision | transcription | none
prompt_version: ...
created_at: ...
---

# 标题

## Source Summary
这份资料是什么、来自哪里、用于什么业务场景。

## Extracted Facts
可被 GBrain 吸收的事实点。

## Entities Mentioned
出现的人、公司、项目、地点、产品等实体名称。

## Events / Timeline Signals
有时间含义的事件、会议、邮件、变更、决策、风险。

## Original Evidence
关键原文摘录、页码、时间戳、附件名、截图区域或表格位置。

## Preprocess Notes
不确定点、缺失、冲突、失败片段、待人工确认事项。
```

各 Skill 可以增加专属章节，但必须保留 evidence，不允许只输出总结。事实、解释和不确定点必须分开。

### 6.3 预处理模型路由

- 纯文本资料处理使用 DeepSeek。
- PDF、截图、图纸、设计图片、视觉版式资料统一使用 MiMo V2.5；不使用 MiMo V2.5 Pro。
- PDF 可做本地文本抽取作为辅助证据，但最终 GBrain-ready Markdown 统一由 MiMo V2.5 生成；纯文本抽取结果不得直接入 GBrain。
- 会议音频/视频先走转写脚本，再进入会议结构化预处理。
- 用户不在前端选择 API Key；Project_R 后端根据文件类型和预处理 Skill 自动路由模型。
- 高影响资料可以输出 `partial` 或 `pending_review`，不得编造补全缺失事实。

---

## 七、Skill 加载与执行

### 7.1 加载

后端启动时 `core/skill_runner.py` 会：
1. 扫描 `backend/skills/builtin/` 与 `backend/skills/enterprise/`
2. 解析每个目录下的 `SKILL.md` 元数据
3. 注册到内存中的 Skill 注册表
4. 把所有 Skill 的 `trigger` 字段汇总，提供给 `/skills/match` 和后续意图识别器；当前产品阶段不启用自然语言自动触发，用户通过 Skill 面板显式选择

管理员上传新的企业 Skill 后调用 `POST /admin/skills/reload` 热加载，无需重启服务。

当前代码级接口为：

- `GET /skills`
- `POST /skills/match`
- `POST /skills/runs`
- `POST /skills/runs/{id}/inputs`
- `GET /skills/runs/{id}`
- `POST /skills/reload`

### 7.2 执行

当前阶段：

```
用户手动选择 Skill → selected_skill 启动 Skill → 收集输入（多轮对话）
        → 执行处理步骤（调用 RAG / LLM / doc_renderer）
        → 输出结果
        → 写入审计日志
```

长期恢复自动意图识别后：

```
用户输入 → 意图识别匹配 Skill → 收集输入（多轮对话）
        → 执行处理步骤（调用 RAG / LLM / doc_renderer）
        → 输出结果
        → 写入审计日志
```

执行过程中 `skill_runner` 会维护 Skill 上下文（已收集的输入），用户可以分多次对话补充信息。

---

## 八、Skill 开发约定

### 8.1 命名

- Skill 目录名 = `name` 字段值（kebab-case），全英文小写
- 模板文件用中文命名，便于管理员识别

### 8.2 引用知识库

- `references` 字段中的链接使用 GBrain source 内的 slug / Markdown 相对路径（例如 `rules/xxx` 或 `rules/xxx.md`），默认 source 为 `company-wiki`
- 后端正式知识源以 GBrain `company-wiki` / 项目 source 为准，不再读取 `backend/knowledge_base/wiki/` 作为运行时知识库
- 执行时这些条目应通过 Project_R 的 GBrain adapter 检索并作为 Skill 上下文；Skill 不应自行调用旧 WikiRouter / Chroma
- 工作区项目资料只服务当前项目成员的项目对话，不混入公司全局知识库

### 8.2.1 上下文优先级

Skill 调用必须遵守 Project_R 的统一上下文优先级：

1. `backend/prompt_presets/global-base-prompt.md` 公司全局底层规则
2. 会话选择提示词 / Agent 模式提示
3. 会话临时附件（本地私人文件必须经用户授权后才可进入 Skill 上下文）
4. 当前工作区项目资料 / GBrain source 检索结果
5. 用户问题与补参输入

全局底层规则是后端强制注入内容，不属于用户可切换提示词；项目资料或附件与全局规则冲突时，以全局规则为准。

Skill 不得默认读取用户本地文件或个人工作台材料。只有用户在当前会话中明确选择附件、确认发送片段/摘要/原文件，或在当前项目/客户工作区内明确引用已有工作区文件后，Skill 才能使用对应内容。个人工作台不提供把附件或生成结果保存到项目/客户资料的跨工作区动作；项目/客户资料的上传、生成、引用和治理应在对应工作区内完成。

预处理 Skill 读取源文件前必须由用户或管理员通过工作区文件面板的“录入”或“录入此文件”显式触发。文件夹录入默认递归当前打开路径及子文件夹，但必须二次确认。

### 8.3 模板路径

- 所有模板路径写相对路径（相对 `backend/`），例如 `templates/word/xxx.docx`
- **严禁写死绝对路径**，否则 Mac mini 迁移会失败

### 8.4 输出文件命名

- 默认格式：`<skill-name>_<项目编号>_<时间戳>.<ext>`
- 项目编号从 `inputs` 中读取，时间戳格式 `YYYYMMDD-HHMMSS`

### 8.5 错误处理

- 任何一步失败不应让对话终止，向用户清晰说明失败原因
- 失败时同样写入审计日志（`是否成功 = false`）

---

## 九、调试 Skill

开发期可以在 Windows 直接调试：

```powershell
cd backend
.\venv\Scripts\Activate.ps1

# 运行后端自动化测试
python -m unittest discover -s tests

# 启动后端后通过对话触发
uvicorn main:app --reload
```

测试输入示例：

```json
{
  "project_code": "BG2026-001",
  "tender_files": ["test/中标通知.pdf", "test/合同草本.docx"]
}
```

---

## 十、与通用 Agent Skill 规范的兼容性

本规范的 SKILL.md frontmatter 字段 (`name` / `description` / `trigger`) 保持通用 Agent Skill 友好结构。这意味着：

- 后期如果要引入更复杂的 Agent 编排，本规范的 Skill 可以被适配层加载
- 当前 MVP 阶段后端用自建的 `skill_runner.py` 即可，不引入完整 Agent SDK

---

## 十一、参考资料

- 本规范的 Skill 示例参见 `backend/skills/builtin/<example>/SKILL.md`
- 标签打印源文件生成已退役，不再作为端到端样板或测试目标。
- 业务工作流清单：`docs/product/Project_R 业务工作流清单.md`
- 产品范围：`docs/product/Project_R PRD.md`
- 阶段进度：`docs/milestones/Project_R 开发流程.md`
- GBrain source repo 新架构：`backend/workspace_data/_preprocessed/.../gbrain-ready/`
- 预处理 Skill 目录说明：`backend/skills/preprocessors/README.md`
- Proma 参考文件不再保留在 Git 仓库内；需要参考时由 Gary 提供本机参考副本或截图
