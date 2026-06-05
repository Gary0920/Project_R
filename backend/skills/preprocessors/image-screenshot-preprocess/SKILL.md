---
name: image-screenshot-preprocess
display_name: 图片 / 截图视觉提炼
description: Extract structured bilingual Markdown from screenshots, site photos, approval-flow images, table screenshots, and business images with MiMo V2.5 vision. Use when preprocessing `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.gif`, `.tif`, or `.tiff` files before writing to `_preprocessed/.../gbrain-ready/`.
category: 资料预处理
priority: high
trigger:
  - image-screenshot-preprocess
  - 图片预处理
  - 截图录入
  - 现场照片录入
  - 表格截图录入
inputs:
  - name: source_path
    type: path
    label: 图片或截图源文件
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
  mode: model_assisted_vision_preprocess
  script: backend/scripts/preprocess_image_screenshot_source.py
  core_module: core.image_structured_extraction
  model_profile: mimo-v2-5
governance:
  risk_level: high
  requires_confirmation: true
  mutates_source_files: false
  triggers_gbrain_sync: false
---

# 图片 / 截图视觉提炼

## Purpose

把图片、截图、现场照片、审批流程图、表格截图、聊天/邮件截图等视觉资料提炼成 GBrain-ready Markdown。此 Skill 使用 MiMo V2.5 视觉能力，不做纯 OCR 直入库，不修改源文件，不自动触发 GBrain sync。

## Trigger Conditions

- 用户或管理员显式触发“录入”或“录入此文件”。
- 文件扩展名为 `.png`、`.jpg`、`.jpeg`、`.webp`、`.bmp`、`.gif`、`.tif` 或 `.tiff`。
- 图片中包含可沉淀的业务事实、流程、表格、现场问题、标注、风险或待确认事项。

## Non-Goals

- 不使用 MiMo V2.5 Pro。
- 不根据模糊区域编造事实。
- 不处理普通装饰图、无业务含义图片或超过大小上限的原图。
- 不自动运行 GBrain sync、Entity Enrichment、graph merge、timeline rebuild、citation-fixer 或 contradiction probe。

## Processing Rules

1. 使用 MiMo V2.5 读取图片内容和可见文字。
2. 稳定事实、流程步骤、字段、责任人、风险和待确认点必须分开。
3. 看不清、被遮挡、分辨率不足、疑似 OCR 错误的内容写入 `Review Questions`。
4. 输出遵守 `bilingual_zh_en_aligned`，中文和 English 表达同一事实。
5. Frontmatter 必须记录 `preprocess_skill=image-screenshot-preprocess`、版本、source 文件、hash、模型、prompt、image kind 和 token usage。

## Verification

- 单元测试应覆盖 prompt 约束、格式支持、大小限制、frontmatter 字段和项目 ingest 写入。
- 质量样板建议放在 `reference/image-screenshot-preprocess/`，至少包含现场照片、审批/流程截图、表格截图和低清晰度图片各 1 个。
