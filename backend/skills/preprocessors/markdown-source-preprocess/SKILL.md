---
name: markdown-source-preprocess
display_name: Markdown / Obsidian 来源清洗
description: Clean Markdown, TXT, Notion export, and Obsidian export files into Project_R GBrain-ready source Markdown with deterministic rules. Use when preprocessing company, project, or CRM Markdown sources before writing to `_preprocessed/.../gbrain-ready/`.
category: 资料预处理
priority: high
trigger:
  - markdown-source-preprocess
  - Markdown 预处理
  - Obsidian 导出清洗
  - Notion 导出清洗
  - TXT 资料录入
inputs:
  - name: raw_path
    type: path
    label: 源文件或源目录
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
  - type: files
    format: markdown
  - type: manifest
    format: json
execution:
  mode: deterministic_script
  script: backend/scripts/preprocess_obsidian_markdown_sources.py
  core_module: core.obsidian_markdown_preprocess
governance:
  risk_level: medium
  requires_confirmation: true
  mutates_source_files: false
  triggers_gbrain_sync: false
---

# Markdown / Obsidian 来源清洗

## Purpose

把 Markdown、TXT、Notion 导出 Markdown 和 Obsidian 导出 Markdown 清洗成 GBrain 友好的 source record Markdown。此 Skill 只做源文件到 `gbrain-ready/` 的确定性预处理，不修改源文件，不自动触发 GBrain sync，不替代 GBrain entity enrichment、graph、timeline 或 citation。

## Trigger Conditions

- 用户或管理员在公司全局知识库、项目工作区或 CRM 客户情报工作区显式触发“录入”或“录入此文件”。
- 文件扩展名为 `.md`、`.markdown` 或 `.txt`。
- 资料主要问题是导出噪音、frontmatter 噪音、Obsidian 双链、图片 embed、空链接或导出残留。

## Non-Goals

- 不使用 DeepSeek 重写、总结或推断正文事实。
- 不保留 `[[...]]` 双链原语法到事实正文。
- 不把 Obsidian 链接直接升级为 GBrain 图谱关系。
- 不处理 PDF、图片、截图、图纸、音视频、EML 或复杂 Excel。
- 不自动运行 GBrain sync、Entity Enrichment、graph merge、timeline rebuild、citation-fixer 或 contradiction probe。

## Processing Rules

1. 读取源文件，保留原始文件不变。
2. 按 Project_R frontmatter 字段治理规则处理源 metadata：核心索引字段保留到输出 frontmatter，叙事/分析字段移到正文，展示噪音、隐私和主观画像字段删除。
3. 将 `[[target|label]]` 转为正文可读文本 `label`，将 `[[target]]` 转为 `target` 的末段名称。
4. 在关系章节记录双链线索，格式为 `label -> target`，供 GBrain 后续原生吸收。
5. 移除 `![[embed]]` 和 Markdown 图片引用，不猜测图片内容，只在证据章节记录被移除引用。
6. 移除明显 HTML span、HTML 注释、水平分隔线和孤立图片 URL 等导出噪音。
7. 只做轻量规则抽取：frontmatter 字段、wikilink label、CRM 目录语义和明确日期字段可进入 entities / timeline signals。

## Frontmatter Policy

保留到输出 frontmatter 的字段：`name`、`type`、`aliases`、`status`、`tags`、`company`、`position`、`role`、`person_type`、`region`、`region_tag`、`city`、`current_phase`、`linked_companies`、`linked_people`、`linked_projects`、`source_events`、`email`、`phone`、`linkedin`、`address`、`start_date`、`end_date_est`、`established`、`internal_id`。

CRM 公司文件额外保留 `market_position`、`employees`、`competitors`、`operation_model`、`pipeline_ecology`；CRM 项目文件额外保留 `budget`。字段合并规则：`operations` / `operations_model` -> `operation_model`；`pipeline` / `pipeline_ecosystem` -> `pipeline_ecology`。

删除字段：`cssclasses`、`cssclass`、`publish`、`draft`、`share`、`dg-publish`、`dg-home`、`age`、`gender`、`family`、`appearance`、`personality`、`habits`、`hobbies`、`personal_ideas`。其他字段默认移入正文 `Source Notes`，不保留在 frontmatter。

## Output Contract

最终 Markdown 必须写入当前 source 的 `_preprocessed/.../gbrain-ready/`，并至少包含：

- `Source Summary`
- `Extracted Facts`
- `Entities Mentioned`
- `Events / Timeline Signals`
- `Original Evidence`
- `Preprocess Notes`

Frontmatter 必须记录 `source_scope`、`source_id`、`source_file`、`source_file_sha256`、`source_file_type`、`preprocess_skill`、`preprocess_version`、`preprocess_status`、`model_profile`、`prompt_version`、`run_id` 和 `created_at`。

## Verification

- 单元测试应覆盖 raw 不被修改、双链转换、embed 移除、frontmatter 噪音移除、manifest 写入和 `dry-run` 不写文件。
- 第一版 fixture 继续放在 `backend/tests/test_obsidian_markdown_preprocess.py`，暂不在 Skill 目录复制样本。
- 脚本入口为 `backend/scripts/preprocess_obsidian_markdown_sources.py`；核心实现为 `backend/core/obsidian_markdown_preprocess.py`。
