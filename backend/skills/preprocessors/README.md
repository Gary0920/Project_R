# Project_R 资料预处理 Skills

本目录用于放置 Project_R 的资料源文件预处理 Skills。

这些 Skills 的职责不是替代 GBrain 知识库系统，而是把 Project_R 中的源文件预处理成 GBrain 友好的 Markdown，写入 `backend/workspace_data/_preprocessed/.../gbrain-ready/`，再由 GBrain 原生 source sync、schema、entity enrichment、graph、timeline、query、think 和 citation 机制吸收。

## 总原则

- 源文件不修改。
- 用户源文件目录不创建 `derived/`。
- 过程文件不出现在普通用户文件面板。
- 过程文件写入 `_preprocessed/.../runs/{preprocess_run_id}/`。
- 最终 Markdown 写入 `_preprocessed/.../gbrain-ready/`，作为 GBrain source repo。
- Manifest 写入 `_preprocessed/.../manifests/`，记录源文件 hash、预处理 Skill、模型、prompt 版本、输出路径、错误和 GBrain sync 状态。
- 每种主要文件类型或业务语义必须独立成 Skill 或脚本，方便单独检查、修改、替换和回归。
- 不做一个万能 ingest Skill。

## 计划中的预处理 Skills

| Skill | 处理对象 | 默认模型 / 流程 | 输出 |
|---|---|---|---|
| `markdown-source-preprocess` | Markdown、TXT、Notion/Obsidian 导出文本 | 规则清洗 + DeepSeek 按需整理 | 保留结构、清理噪音、补来源和证据 |
| `docx-text-preprocess` | Word `.docx` 文档、会议纪要、文本记录、表格文本 | python-docx 确定性抽取 | 段落、表格、轻量时间线信号和证据 |
| `pdf-structured-preprocess` | 所有 PDF | 文本抽取作辅助证据 + MiMo V2.5 | 结构化 Markdown、页码证据、不确定点 |
| `drawing-pdf-vision-preprocess` | 图纸 PDF、楼层图、总平图、技术版式 PDF | MiMo V2.5 | 图纸/版式语义、关键标注、风险和证据 |
| `image-screenshot-preprocess` | 图片、截图、审批流、表格图片、现场照片 | MiMo V2.5 | 图片内容、可见文字、区域说明、待确认点 |
| `meeting-audio-video-preprocess` | 已有 transcript 的会议资料、无 transcript 的音频/视频、VTT/SRT | transcript sidecar 或 MiMo V2.5 转写 + 结构化提炼 | transcript 过程文件、会议决策、行动项、风险、证据和待审核问题 |
| `email-thread-preprocess` | EML、邮件线程、邮件附件关系 | 邮件解析 + DeepSeek；附件递归调度 | 邮件事实、决策、行动项、参与人、附件索引 |
| `spreadsheet-preprocess` | Excel、CSV、TSV、报价表、联系人表、清单 | B1 第一版只标记 `pending_capability`；后续再实现表格抽取 | 暂不产出 GBrain-ready Markdown，manifest 保留待处理状态 |
| `archive-preprocess` | ZIP/RAR/文件包 | 展开、分类、调度其他 Skill | 通常不直接产出最终知识 Markdown |
| `customer-intelligence-source-preprocess` | 客户邮件、会议、联系人、公司/项目关系资料 | 调用上方格式 Skill + GBrain 友好客户来源记录模板 | 面向 GBrain enrich/entity detection 的客户情报来源 Markdown |

## 最低输出模板

每个预处理 Skill 的最终 Markdown 至少包含：

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

各 Skill 可以增加专属章节，但不能删除最低模板中的证据、不确定性和来源字段。

## 模型路由

- 纯文本资料使用 DeepSeek。
- PDF、截图、图纸、设计图片和视觉版式资料统一使用 MiMo V2.5。
- 不使用 MiMo V2.5 Pro。
- PDF 可先做本地文本抽取作为辅助证据，但最终 Markdown 统一由 MiMo V2.5 生成。
- 会议音频/视频先走转写脚本，再进入会议结构化预处理。
- 用户不选择 API Key；Project_R 后端按文件类型和 Skill 自动路由。

## 不做什么

- 不修改 GBrain 成熟架构。
- 不替代 GBrain schema pack、entity enrichment、graph、timeline、query、think 或 citation。
- 不直接生成最终 `people/`、`companies/`、`projects/` 画像页，除非 GBrain 原生流程明确要求这种输入形态。
- 不把纯 PDF 文本抽取结果直接写入 GBrain。
- 不因源文件删除而自动删除 GBrain-ready Markdown。

## 新增 Skill 要求

新增预处理 Skill 时必须提供：

- `SKILL.md` 或脚本入口说明。
- 支持的文件类型和拒绝的文件类型。
- 输入、输出、过程文件清单。
- 模型路由和 prompt 版本。
- 至少一个真实或可复现样本回归。
- 验收标准：关键字段、evidence、uncertainties、manifest 状态和 GBrain sync 结果。
