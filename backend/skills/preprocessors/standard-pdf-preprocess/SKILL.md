---
name: standard-pdf-preprocess
display_name: 标准规范 PDF 知识库提炼
description: Extract objective, traceable standard/specification knowledge from general PDF standards into an 11-section Markdown knowledge base for GBrain RAG. Use for standards and specifications that should become factual requirement libraries, not project execution advice.
category: 资料预处理
priority: high
trigger:
  - standard-pdf-preprocess
  - 标准 PDF 提炼
  - 规范 PDF 提炼
  - 标准规范录入
  - 规范知识库
inputs:
  - name: source_path
    type: path
    label: 标准规范 PDF 源文件
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
  core_module: app.features.preprocessing.pdf_structured
  model_profile: mimo-v2-5
governance:
  risk_level: high
  requires_confirmation: true
  mutates_source_files: false
  triggers_gbrain_sync: false
---

# 标准规范 PDF 知识库提炼

## Purpose

把标准、规范、测试方法、技术要求类 PDF 提炼成 GBrain-ready Markdown。输出是客观、可追溯、可检索的 Standard Knowledge Base，不是项目执行手册、经验库或行业建议。

## Trigger Conditions

- 文件扩展名为 `.pdf`。
- PDF 被分类为 `general_pdf`，不属于图纸、门窗表、总平面、施工图、排期表等视觉版式依赖 PDF。
- 资料目标是进入规范事实库，用于 RAG 检索和 AI 问答。

## Processing Rules

1. PDF 文本抽取只作为辅助证据；最终正文必须由 MiMo V2.5 结构化生成。
2. 每条知识必须标注标准编号、条款号和页码证据。
3. 输出按 11 个固定分区组织：Scope、Referenced Standards、Definitions、Terms Library、Symbols Library、Requirements Library、Formula Library、Parameter Library、Table Library、Verification Methods、Source Mapping。
4. 数学公式使用 LaTeX；关键表格必须完整保留为 Markdown 表格，不得只写“见原表”。
5. 禁止输出项目建议、实施建议、风险提示、推荐做法、项目经验、行业经验、设计建议或施工建议。
6. 无法确认、OCR/版式不可靠、表格错位或视觉证据不足的内容写入 `待审核问题 / Review Questions`。

## Output Contract

Frontmatter 必须记录 `preprocess_skill=standard-pdf-preprocess`、`preprocess_version`、`preprocess_status`、`prompt_version`、`model_profile`、`language_policy`、原始 PDF 路径/hash、页数、已分析页数、视觉页和 review 状态。

项目 source 中的标准 PDF 默认保持 `review_status=pending_review`，由人工审核后再进入可信引用链路。

## Verification

- 单元测试必须覆盖 11 分区 prompt、可追溯要求、LaTeX、表格保留和禁止主观建议。
- 回归中必须确认图纸/版式 PDF 仍使用 `drawing-pdf-vision-preprocess`，不误套标准规范模板。
