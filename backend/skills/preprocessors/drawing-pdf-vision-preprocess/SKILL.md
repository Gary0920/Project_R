---
name: drawing-pdf-vision-preprocess
display_name: 图纸 / 版式 PDF 视觉提炼
description: Extract structured bilingual Markdown from drawing PDFs, floor plans, window schedules, facade details, and layout-heavy technical PDFs with MiMo V2.5 vision. Use when PDF meaning depends on drawing layout, tables, annotations, sheet coordinates, or visual evidence.
category: 资料预处理
priority: high
trigger:
  - drawing-pdf-vision-preprocess
  - 图纸 PDF 提炼
  - 平面图录入
  - 门窗表录入
  - 节点图录入
inputs:
  - name: source_path
    type: path
    label: 图纸或版式 PDF
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
  script: backend/scripts/preprocess_drawing_pdf_vision_source.py
  core_module: core.pdf_structured_extraction
  model_profile: mimo-v2-5
governance:
  risk_level: high
  requires_confirmation: true
  mutates_source_files: false
  triggers_gbrain_sync: false
---

# 图纸 / 版式 PDF 视觉提炼

## Purpose

处理意义依赖视觉版式的 PDF，例如工程平面图、总平图、立面/节点图、门窗表、技术排版 PDF 和扫描型图纸。此 Skill 复用 PDF structured core，但在分类和 frontmatter 中标记为独立的 `drawing-pdf-vision-preprocess`。

## Trigger Conditions

- 文件名或内容显示为 drawing、general arrangement、plan、facade、detail/details、window schedule、sheet、图纸、平面图、立面图、节点图等。
- PDF 有同名页图像侧车，或可选文本不足以表达图纸/表格/标注含义。
- 资料需要页码、图纸号、标注、表格、区域或版式位置作为证据。

## Non-Goals

- 不用纯 PDF 文本抽取直接入库。
- 不使用 MiMo V2.5 Pro。
- 不把图纸解释成最终设计结论；不确定内容必须进入 review questions。
- 不自动运行 GBrain sync、Entity Enrichment、graph merge、timeline rebuild、citation-fixer 或 contradiction probe。

## Processing Rules

1. PDF 文本抽取只作为辅助证据。
2. 优先使用 MiMo V2.5 视觉能力理解图纸版式、门窗表、标注和节点关系。
3. 输出必须遵守 `bilingual_zh_en_aligned`，每个关键事实尽量带页码、图纸号或表格/区域证据。
4. 图纸不清晰、标注冲突、表格错位、版本号不确定、无法读取的区域必须写入 `Review Questions`。
5. 项目 source 可按项目权限直接写入当前项目 GBrain-ready repo，但 frontmatter 必须保留 extractor review status 和视觉页信息。

## Verification

- 参考样本位于 `reference/pdf-structured-preprocess/视觉版式依赖 PDF/`。
- 回归应确认这些样本被分类为 `vision_required / mimo_vision`，不会走 `text_assisted` 或纯文本入库。
