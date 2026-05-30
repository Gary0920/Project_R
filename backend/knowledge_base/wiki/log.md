---
title: "操作日志"
type: rule
content_kind: reference
source_folder: ""
source_domain: internal_rule
authority_level: internal_policy
extraction_status: native_text
aliases: [log, 日志]
tags: []
sources: []
last_updated: 2026-04-27
---

# 操作日志

## [2026-04-27] ingest | 首次全量导入 — 批量处理 raw/ 全部未归档文件

### 处理范围

| 分类      | 原始目录                                    | 处理文件数            | 产出                                                     |
| ------- | --------------------------------------- | ---------------- | ------------------------------------------------------ |
| 公司规则    | raw/01-Company Rules/                   | 18 规则 + 2 描述     | wiki/rules/ (18), wiki/tags/ (1), wiki/rules/公司规则总览.md |
| 公司流程    | raw/02-Company Procedures List/         | 11 流程 + 2 描述     | wiki/rules/ (11), wiki/tags/ (1), wiki/rules/公司流程总览.md |
| 项目规则与流程 | raw/03-Project Rules & Procedures List/ | 72 规则 + 4 描述     | wiki/rules/ (72), wiki/tags/ (3), wiki/rules/项目规则总览.md |
| 培训资料    | raw/04-Training List/                   | ~100 文件 → 75 知识页 | wiki/training/ (75), wiki/sources/ (75)                |
| 行业规范    | raw/06-Standards/                       | 321 文件           | wiki/standards/ (4), wiki/sources/ (8)                 |

### 产出一览

- wiki/sources/：约 195 个来源卡
- wiki/rules/：约 107 个知识页
- wiki/training/：约 75 个知识页
- wiki/standards/：4 个页面
- wiki/tags/：5 个标签页

### 注意事项

- 访客接待流程、客户来访准备流程为 Draft 空文件，标记 manual_review_needed
- 澳洲对 BFI 开票免税 已废止，引用替代规则含GST澳洲本地费用报销
- 所有 PDF 标准文件标记 attachment_only
- 所有培训页标注为经验分享，不等同于正式制度
- 未发现需要暂停的知识冲突

## [2026-04-27] ingest | 归档已完成 — 移动已处理文件到 raw/99-archive/

归档范围：raw/01-Company Rules/、raw/02-Company Procedures List/、raw/03-Project Rules & Procedures List/、raw/04-Training List/、raw/06-Standards/ 下全部已处理文件。

排除文件（保留在 raw/ 原位，待人工处理）：
- raw/02-Company Procedures List/New database/访客接待流程.md（Draft 空文件）
- raw/02-Company Procedures List/New database/客户来访准备流程.md（Draft 空文件）

归档后 raw/ 目录中仅保留上述2个待处理文件，其余全部移至 raw/99-archive/ 保持原目录结构。
