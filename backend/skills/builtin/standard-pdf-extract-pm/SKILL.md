---
name: standard-pdf-extract-pm
display_name: 规范 PDF 提炼-PM版（项目执行型知识库）
description: 将标准规范 PDF 转换为项目经理执行型知识库，按规范作用类型（A-H）重新组织，每条内容含 8 字段执行卡片。适用门窗/幕墙/玻璃/五金/表面处理/安装/防水/测试/认证等规范。
category: 知识管理
priority: high
trigger:
  - 项目经理版
  - PM版
  - 执行手册
  - 项目执行知识库
  - 规范类型分类
  - PM extract
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
    description: 项目执行型知识库 Markdown（按 A-H 规范作用类型组织）
execution:
  mode: pdf_structured_extract
  engine: standard-pdf-preprocess
  params:
    skill: standard-pdf-preprocess-pm
    model_profile: mimo-v2-5
    split_threshold_pages: 40
    extraction_version: B
governance:
  risk_level: low
  requires_confirmation: false
  allowed_tools:
    - pdf.structured_extract
    - llm.complete
---
