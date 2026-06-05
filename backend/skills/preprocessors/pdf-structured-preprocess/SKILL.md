---
name: pdf-structured-preprocess
display_name: PDF 结构化资料提炼
description: Extract structured bilingual Markdown from PDF files with MiMo V2.5 and optional page-image evidence. Use when preprocessing PDF standards, specifications, reports, or selectable PDFs before writing to `_preprocessed/.../gbrain-ready/`.
category: 资料预处理
priority: high
trigger:
  - pdf-structured-preprocess
  - PDF 结构化提炼
  - PDF 录入
  - PDF 预处理
inputs:
  - name: source_path
    type: path
    label: PDF 源文件
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
  mode: model_assisted_preprocess
  script: backend/scripts/preprocess_pdf_structured_source.py
  core_module: core.pdf_structured_extraction
  model_profile: mimo-v2-5
governance:
  risk_level: high
  requires_confirmation: true
  mutates_source_files: false
  triggers_gbrain_sync: false
---

# PDF 结构化资料提炼

## Purpose

把 PDF 提炼成 GBrain-ready Markdown。此 Skill 使用 PDF 文本抽取作为辅助证据，并可结合同名页图像侧车或视觉页；最终知识正文必须由 MiMo V2.5 辅助结构化生成，不能把纯 PDF 文本抽取结果直接写入 GBrain 查询面。

## Trigger Conditions

- 用户或管理员显式触发“录入”或“录入此文件”。
- 文件扩展名为 `.pdf`。
- PDF 是标准、规范、报告、技术说明、项目资料或其他需要结构化提炼的资料。

## Non-Goals

- 不使用 MiMo V2.5 Pro。
- 不逐页复刻原文，不把 PDF raw text 直接作为最终正文。
- 不自动批准公司全局知识库 pending review。
- 不自动运行 GBrain sync、Entity Enrichment、graph merge、timeline rebuild、citation-fixer 或 contradiction probe。

## Processing Rules

1. 读取 PDF 页数和可抽取文本；文本只作为辅助证据。
2. 如配置视觉页或同名页图像侧车，加载关键页图像作为视觉辅助。
3. 使用 MiMo V2.5 生成中英双语对齐 Markdown，遵守 `bilingual_zh_en_aligned`。
4. 不确定、表格错位、OCR 异常、图示依赖和证据不足内容必须放入 review questions。
5. 公司全局 PDF 默认输出 `pending_review`；项目 PDF 可按项目 source policy 直接进入项目 source，但保留 extractor review status。

## Output Contract

Frontmatter 必须记录 `preprocess_skill=pdf-structured-preprocess`、`preprocess_version`、`preprocess_status`、`prompt_version`、`model_profile`、`language_policy`、原始 PDF 路径/hash、页数、已分析页数、视觉页和 review 状态。

## Verification

- 单元测试应覆盖中英双语校验、prompt 约束、company pending review frontmatter、project source frontmatter。
- 回归中必须确认 PDF 文本抽取不会绕过 MiMo 结构化提炼直接写入 GBrain-ready 正文。
