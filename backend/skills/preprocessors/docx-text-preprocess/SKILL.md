---
name: docx-text-preprocess
display_name: DOCX 文本来源提取
description: Extract paragraphs and tables from DOCX files into Project_R GBrain-ready source Markdown with deterministic rules. Use when preprocessing Word `.docx` company, project, or CRM source files before writing to `_preprocessed/.../gbrain-ready/`.
category: 资料预处理
priority: high
trigger:
  - docx-text-preprocess
  - DOCX 预处理
  - Word 文档录入
  - Word 文本提取
inputs:
  - name: source_path
    type: path
    label: DOCX 源文件
    required: true
  - name: source_scope
    type: select
    label: Source scope
    required: true
    options: [company, project, customer]
  - name: source_id
    type: text
    label: GBrain source id
    required: true
outputs:
  - type: file
    format: markdown
execution:
  mode: deterministic_script
  script: backend/scripts/preprocess_docx_text_sources.py
  core_module: core.docx_text_preprocess
governance:
  risk_level: medium
  requires_confirmation: true
  mutates_source_files: false
  triggers_gbrain_sync: false
---

# DOCX 文本来源提取

## Purpose

把 `.docx` 中可读取的段落和表格提取为 GBrain-ready Markdown。此 Skill 只做确定性文本/表格抽取，不修改源文件，不自动触发 GBrain sync，不使用模型总结或重写。

## Trigger Conditions

- 用户或管理员显式触发“录入”或“录入此文件”。
- 文件扩展名为 `.docx`。
- DOCX 主要内容是会议纪要、项目说明、报价说明、文本记录或表格化文本。

## Non-Goals

- 不处理 `.doc`、PDF、图片型扫描件、嵌入图片、批注、修订痕迹或复杂版式。
- 不使用 DeepSeek 总结、补全、推断行动项或改写事实。
- 不自动运行 GBrain sync、Entity Enrichment、graph merge、timeline rebuild、citation-fixer 或 contradiction probe。

## Processing Rules

1. 使用 `python-docx` 读取非空段落。
2. 使用 Markdown table 保留 DOCX 表格文本；单元格换行转换为 `<br>`。
3. 只从明确日期模式中抽取轻量 timeline signals。
4. 输出 `Source Summary`、`Extracted Facts`、`Entities Mentioned`、`Events / Timeline Signals`、`Original Evidence`、`Preprocess Notes`。
5. Frontmatter 记录 `preprocess_skill=docx-text-preprocess`、版本、source scope、source id、原文件 hash、段落数、表格数和 `language_policy=bilingual_zh_en_aligned`。

## Verification

- 单元测试应覆盖段落提取、表格提取、最低模板章节、frontmatter、源文件不修改。
- 公司和项目 ingest 复用 `core.docx_text_preprocess`，不得继续维护各自内联 DOCX 编译逻辑。
