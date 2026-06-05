---
name: email-thread-preprocess
display_name: 邮件线程结构化提炼
description: Parse EML email threads, extract project/customer facts into bilingual Markdown, and optionally unpack attachments for recursive preprocessing. Use when preprocessing `.eml` project or CRM email files before writing to `_preprocessed/.../gbrain-ready/`.
category: 资料预处理
priority: high
trigger:
  - email-thread-preprocess
  - EML 邮件录入
  - 邮件线程提炼
  - 邮件附件递归
inputs:
  - name: source_path
    type: path
    label: EML 邮件源文件
    required: true
  - name: source_scope
    type: select
    label: Source scope
    required: true
    options: [project, customer, company]
  - name: source_id
    type: text
    label: GBrain source id
    required: true
outputs:
  - type: file
    format: markdown
execution:
  mode: model_assisted_text_preprocess
  script: backend/scripts/preprocess_email_thread_source.py
  core_module: core.email_structured_extraction
  model_profile: deepseek-flash
governance:
  risk_level: high
  requires_confirmation: true
  mutates_source_files: false
  triggers_gbrain_sync: false
---

# 邮件线程结构化提炼

## Purpose

把 `.eml` 邮件线程提炼成 GBrain-ready Markdown，并在用户确认时展开附件，让附件按自身文件类型递归进入对应 preprocessor。此 Skill 只处理邮件事实、参与人、时间、附件关系、行动项、风险和待确认点，不替代后续 GBrain entity enrichment。

## Trigger Conditions

- 用户或管理员显式触发“录入”或“录入此文件”。
- 文件扩展名为 `.eml`。
- 邮件属于项目沟通、客户沟通、现场问题、报价/变更/投诉/审批/技术确认等业务场景。

## Non-Goals

- 第一版不正式解析 `.msg`、`.mbox`；这些类型保持 `pending_extractor_capability`。
- 不把附件内容塞进邮件正文；附件应展开后按文件类型递归预处理。
- 不编造邮件没有表达的责任、承诺、VO/EOT/back-charge 结论。
- 不自动运行 GBrain sync、Entity Enrichment、graph merge、timeline rebuild、citation-fixer 或 contradiction probe。

## Processing Rules

1. 解析 subject、from、to/cc、date、纯文本/HTML body 和附件文件名。
2. 默认使用 DeepSeek profile 结构化提炼；模型不可用时使用确定性 fallback Markdown。
3. 输出必须遵守 `bilingual_zh_en_aligned`，并区分事实、行动项、风险和待确认事项。
4. 启用附件递归时，把附件写入 `{email_stem}.attachments/`，由外层 ingest 继续分类调度。
5. Frontmatter 必须记录 `preprocess_skill=email-thread-preprocess`、版本、source 文件、hash、邮件头字段、附件列表、模型和 token usage。

## Verification

- 单元测试应覆盖 EML 解析、fallback 输出、项目 source 写入 frontmatter、附件展开和递归调度。
- 质量样板建议放在 `reference/email-thread-preprocess/`，至少包含普通项目邮件、带附件邮件、HTML 邮件、长线程邮件各 1 个。
