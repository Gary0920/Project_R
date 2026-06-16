---
name: client-reply-drafting
display_name: 客户英文回复起草
description: 根据澳洲门窗幕墙项目邮件、顾问意见、现场质量反馈、物流问题或VO/EOT/claim争议，起草专业、克制、保留责任边界的英文回复邮件
category: 跨阶段通用业务
priority: high
trigger:
  - 起草英文回复
  - 帮我回复客户
  - 回复客户投诉
  - 回复顾问comment
  - 回复builder催促
  - 回复VO争议
  - 回复claim争议
  - 回复现场质量反馈
  - 回复图纸修改要求
  - client-reply-drafting
inputs:
  - name: reply_brief
    type: text
    label: 原始邮件/背景与我方立场
    required: true
  - name: tone
    type: select
    label: 回复语气
    required: false
    options: [friendly, neutral, firm, cautious, urgent]
outputs:
  - type: chat_text
    format: markdown
  - type: file
    format: eml
    optional: true
    description: 用户确认邮件草稿后，可通过 Project_R 邮件草稿能力生成 .eml 文件
references:
  - rules/项目邮件相关规则.md
  - rules/项目沟通与书面留痕原则.md
execution:
  mode: llm_chat_text
  prompt: prompt.md
  steps:
    - id: compose_context
      label: 组装会话附件与项目知识上下文
      tool: project_r.context.compose
    - id: knowledge_search
      label: 检索项目沟通规则
      tool: knowledge.search
    - id: llm_complete
      label: 生成英文回复草稿
      tool: llm.complete
    - id: optional_email_draft
      label: 用户确认后生成邮件草稿文件
      tool: project_r.document.render
      optional: true
governance:
  risk_level: medium
  requires_confirmation: false
  allowed_tools:
    - project_r.context.compose
    - knowledge.search
    - llm.complete
    - project_r.document.render
---

# 客户英文回复起草

## 目的

帮助项目经理在已经明确我方立场时，把中文内部判断或项目背景转化为可直接发送给澳洲 Builder、Developer、Consultant、Engineer、Architect、Installer、物流方、供应商或工厂的英文邮件回复。

本 Skill 的重点不是逐句翻译，而是输出技术准确、商业克制、语气自然且不轻易承认责任的英文回复。

## 触发条件

- **必要前置条件**：用户已提供原始邮件、问题背景或至少说明我方准备采取的立场。
- **典型触发语**：
  - "帮我回复客户这封邮件"
  - "把我方立场整理成英文回复"
  - "回复顾问 comment，语气专业一点"
  - "这个 VO 争议帮我写一封英文邮件"
  - "客户投诉现场质量问题，帮我回邮件"
- **非触发场景**：
  - 用户只要求翻译原文，不需要项目管理判断。
  - 用户还没有明确我方立场，只想先判断对方邮件风险；应优先使用 `project-communication-analysis`。

## 输入收集步骤

1. 收集原始邮件、客户问题或现场背景。
2. 确认收件对象和我方意图：接受、拒绝、澄清、延后确认、升级处理或提出替代方案。
3. 确认语气：friendly、neutral、firm、cautious 或 urgent；未提供时默认 professional and commercially cautious。
4. 如涉及成本、工期、责任、VO、EOT、claim、back charge 或 delay risk，先提示用户这些点需要保留立场。

## 处理步骤

1. 读取同目录 `prompt.md` 作为核心写作指令。
2. 识别原文中的事实、我方立场、风险点和需要进一步确认的事项。
3. 按 `prompt.md` 要求输出回复策略、英文邮件草稿、中文说明和必要的强/弱替代表达。
4. 对不确定事实使用 conditional wording，避免过度承诺。
5. 对责任、费用、工期或合规结论保持边界，除非用户明确要求承认或承诺。

## 输出形式

- **主输出**：聊天文本 / Markdown。
- **可选文件输出**：用户确认草稿后，可生成邮件草稿 `.eml`，供下载、复制正文或打开默认邮件客户端。
- **固定结构**：
  1. Reply Strategy
  2. English Email Draft
  3. 中文说明
  4. Optional Stronger / Softer Alternatives（仅在有价值时输出）

`English Email Draft` 必须包含清晰的 `Subject:` 和完整正文。若用户提供收件人、抄送人或密送人，应保留为结构化字段，供 Sprint 6 邮件草稿卡使用。

## 错误处理

| 失败点 | 处理方式 |
|---|---|
| 原始背景不足 | 先列出假设，再给出 best-effort draft；关键风险缺口必须提示用户 |
| 我方立场不清 | 先追问用户希望接受、拒绝、澄清、保留立场还是提出替代方案 |
| 涉及责任/费用/工期风险 | 默认不承认责任，不承诺费用或工期，使用谨慎表达 |
| 用户要求强硬回复 | 可以给 firmer wording，但避免攻击性、情绪化和无法支撑的法律判断 |

## 关联知识与上下文

- `rules/项目邮件相关规则.md`：用于项目邮件标题、书面沟通和项目名称规范。
- `rules/项目沟通与书面留痕原则.md`：用于确认所有关键立场应保留书面记录。
- 当前工作区项目资料和会话附件只作为当前项目上下文，不得引用其他项目资料。

## 测试用例

见 `examples/` 目录。

## 维护说明

- 长提示词只维护在 `prompt.md`，避免在 `SKILL.md` 中重复大段写作规则。
- 修改本 Skill 时同步更新根目录 `Project_R 业务工作流清单.md` 中对应状态与链接。
