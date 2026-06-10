---
name: meeting-actions
display_name: 行动项提炼
description: 从会议转录文本或纪要中提炼行动项，包括负责人、截止时间和依赖条件。适用项目/CRM 工作区。
category: 项目协作
priority: high
trigger:
  - 提炼行动项
  - 提取行动项
  - 会议行动项
  - 帮我列行动项
  - meeting-actions
inputs:
  - name: folder_path
    type: text
    label: 会议文件夹路径（如 20-会议与沟通/20260610-0930-项目启动会）
    required: false
  - name: content
    type: text
    label: 转录文本、纪要或行动项要点
    required: false
outputs:
  - type: chat_text
    format: markdown
execution:
  mode: llm_chat_text
  prompt: prompt.md
  steps:
    - id: compose_context
      label: 组装会议上下文
      tool: project_r.context.compose
    - id: llm_complete
      label: 提炼行动项
      tool: llm.complete
governance:
  risk_level: low
  requires_confirmation: false
  allowed_tools:
    - project_r.context.compose
    - llm.complete
---
