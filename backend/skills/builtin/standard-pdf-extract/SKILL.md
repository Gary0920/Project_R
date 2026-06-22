---
name: standard-pdf-extract
display_name: 规范 PDF 提炼（规范知识库）
description: 将标准规范 PDF 转换为结构化规范知识库，专用于 RAG 检索和 AI 问答。输出按 11 分区组织：术语库、符号库、要求库、公式库、参数库、表格库、验证方法、来源映射等。纯事实，无项目建议。适用项目/CRM 工作区。
category: 知识管理
priority: high
trigger:
  - 提炼标准
  - 提取标准
  - 标准 PDF 提炼
  - 规范提炼
  - standard extract
  - PDF 提炼
  - 知识库提炼
inputs:
  - name: pdf_path
    type: file
    label: 标准规范 PDF 文件路径
    required: true
    accept: .pdf
  - name: output_dir
    type: text
    label: 输出目录（默认与 PDF 同目录）
    required: false
outputs:
  - type: file
    format: markdown
    description: 结构化规范知识库 Markdown（11 分区：Scope/Definitions/Terms/Symbols/Requirements/Formulas/Parameters/Tables/Verification/SourceMapping）
execution:
  mode: pdf_structured_extract
  engine: standard-pdf-preprocess
  steps:
    - id: extract
      label: 提取规范知识库
      tool: pdf.structured_extract
      params:
        skill: standard-pdf-preprocess
        model_profile: mimo-v2-5
        split_threshold_pages: 40
governance:
  risk_level: low
  requires_confirmation: false
  allowed_tools:
    - pdf.structured_extract
    - llm.complete
---
