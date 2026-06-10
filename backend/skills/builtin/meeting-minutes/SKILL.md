---
name: meeting-minutes
display_name: 项目会议纪要整理
description: 从会议转录文本中提取关键信息，生成结构化的会议纪要和行动项。适用项目/CRM 工作区。
category: 项目协作
priority: high
trigger:
  - 整理会议纪要
  - 生成会议纪要
  - 会议总结
  - 帮我写会议纪要
  - meeting-minutes
inputs:
  - name: folder_path
    type: text
    label: 会议文件夹路径（如 20-会议与沟通/20260610-0930-项目启动会）
    required: true
  - name: content
    type: text
    label: 转录文本或会议要点
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
      label: 生成会议纪要
      tool: llm.complete
governance:
  risk_level: low
  requires_confirmation: false
  allowed_tools:
    - project_r.context.compose
    - llm.complete
---
