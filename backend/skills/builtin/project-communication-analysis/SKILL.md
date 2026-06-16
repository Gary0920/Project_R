---
name: project-communication-analysis
display_name: 项目沟通风险分析
description: 分析澳洲门窗幕墙项目邮件、顾问comment、现场问题、客户投诉和商务争议，判断真实意图、技术/进度影响、VO/EOT/back-charge风险与下一步动作
category: 跨阶段通用业务
priority: high
trigger:
  - 项目沟通分析
  - 分析客户邮件
  - 帮我判断这封邮件风险
  - 顾问comment分析
  - 现场问题风险分析
  - VO风险分析
  - EOT风险分析
  - back-charge风险分析
  - project-communication-analysis
inputs:
  - name: communication_text
    type: text
    label: 原始沟通内容
    required: true
  - name: project_context
    type: text
    label: 项目背景/已知上下文
    required: false
outputs:
  - type: chat_text
    format: markdown
references:
  - rules/项目邮件相关规则.md
  - rules/项目沟通与书面留痕原则.md
execution:
  mode: llm_chat_text
  prompt: prompt.md
  steps:
    - id: compose_context
      label: 组装沟通原文与项目上下文
      tool: project_r.context.compose
    - id: knowledge_search
      label: 检索沟通与书面留痕规则
      tool: knowledge.search
    - id: llm_complete
      label: 生成项目沟通风险分析
      tool: llm.complete
governance:
  risk_level: medium
  requires_confirmation: false
  allowed_tools:
    - project_r.context.compose
    - knowledge.search
    - llm.complete
---

# 项目沟通风险分析

## 目的

帮助项目经理阅读复杂邮件、顾问 comment、现场问题、客户投诉、RFI/NCR/QA 反馈和商务争议，判断对方真实意图、技术含义、商业风险和下一步处理动作。

本 Skill 的重点不是翻译，而是区分事实、假设、风险和建议，避免项目团队在不清楚责任、成本或工期影响前贸然回复。

## 触发条件

- **必要前置条件**：用户提供原始邮件、comment、会议纪要、现场反馈或争议沟通内容。
- **典型触发语**：
  - "帮我分析这封客户邮件"
  - "这个顾问 comment 到底想要我们做什么"
  - "这件事有没有 VO / EOT 风险"
  - "客户投诉现场质量问题，帮我判断下一步"
  - "这封邮件能不能直接回复"
- **非触发场景**：
  - 用户只要求把邮件翻译成中文或英文。
  - 用户已经明确立场并要求生成英文回复；应使用 `client-reply-drafting`。

## 输入收集步骤

1. 收集原始沟通内容。
2. 如用户未提供，提示可补充项目阶段、图纸版本、现场位置、责任背景、已批准文件或合同边界。
3. 如果原文信息不足，不强行判断责任或结论，只列出需要澄清的信息。

## 处理步骤

1. 读取同目录 `prompt.md` 作为核心分析指令。
2. 识别沟通类型、发送方核心诉求、文本明确事实和隐含压力。
3. 分析技术影响、采购/生产/发货/现场安装影响和工期风险。
4. 分析商业/合同风险，尤其是 VO、EOT、back charge、delay、NCR、rejection、liability 和 scope creep。
5. 给出 BFI 建议立场、禁止表达和下一步动作。

## 输出形式

- **主输出**：聊天文本 / Markdown。
- **固定结构**：
  1. Communication Type
  2. Core Intent
  3. Key Facts Confirmed by the Text
  4. Technical Impact
  5. Programme / Procurement / Production Impact
  6. Commercial / Contractual Risk
  7. Missing Information / Clarifications Required
  8. Recommended BFI Position
  9. What to Avoid Saying
  10. Suggested Next Steps

如果分析结果已经形成清晰的建议立场，应在 `Suggested Next Steps` 中提示：用户确认立场后，可继续使用 `client-reply-drafting` 生成客户英文回复草稿。不要在本 Skill 内直接代替用户发送或承诺回复。

## 错误处理

| 失败点 | 处理方式 |
|---|---|
| 原文内容太短 | 明确说明资料不足，只给有限判断和需补充信息 |
| 事实与假设混杂 | 分开列出 confirmed facts、assumptions、risks 和 recommendations |
| 涉及法律责任 | 不给法律意见，只从项目管理和商业沟通角度提示风险 |
| 缺少图纸/版本/位置 | 将其列入 Missing Information，不得编造 |

## 关联知识与上下文

- `rules/项目邮件相关规则.md`：用于判断项目邮件沟通是否满足基本书面规范。
- `rules/项目沟通与书面留痕原则.md`：用于提醒关键结论、指令和责任边界必须书面留痕。
- 当前工作区项目资料和会话附件只作为当前项目上下文，不得引用其他项目资料。

## 测试用例

见 `examples/` 目录。

## 维护说明

- 长分析规则只维护在 `prompt.md`，避免在 `SKILL.md` 中重复大段业务判断标准。
- 修改本 Skill 时同步更新根目录 `Project_R 业务工作流清单.md` 中对应状态与链接。
