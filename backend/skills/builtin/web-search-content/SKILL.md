---
name: web-search-content
display_name: 联网搜索内容
description: 在用户显式开启联网搜索时，搜索公开网页并把结果摘要注入 DeepSeek / MiMo 对话上下文。
category: Chat 工具
priority: medium
trigger:
  - 联网搜索
  - 搜索网络资料
  - 查一下最新信息
  - 帮我联网查
inputs:
  - name: query
    type: text
    label: 搜索问题
    required: true
outputs:
  - type: chat_text
    format: markdown
execution:
  mode: web_search_context
  tool: web_search.search
governance:
  visibility: internal
  risk_level: medium
  requires_confirmation: false
  allowed_tools:
    - web_search.search
references: []
---

# 联网搜索内容

## 目的

当用户在聊天输入区打开“联网搜索”开关时，Project_R 使用本 Skill 对本轮用户问题进行公开网页搜索，并把搜索结果摘要作为上下文交给当前模型。

## 适配模型

- DeepSeek：以文本 system prompt 方式注入网页摘要。
- MiMo：同样以文本上下文注入，不依赖模型原生联网能力。

## 处理步骤

1. 使用本轮用户消息作为搜索 query。
2. 调用后端配置的搜索 provider。
3. 取前 5 条结果，保留标题、URL 和摘要。
4. 将结果格式化为 `[来源 N]` 引用块注入模型上下文。
5. 模型回答时应基于摘要给出结论，并在关键结论后标注 `[来源 N]`。

## 搜索 Provider

默认 provider 为 `duckduckgo`。可通过环境变量切换：

- `WEB_SEARCH_PROVIDER=duckduckgo`
- `WEB_SEARCH_PROVIDER=bing`，需要 `BING_SEARCH_API_KEY`
- `WEB_SEARCH_PROVIDER=serper`，需要 `SERPER_API_KEY`

## 错误处理

- 搜索失败或无结果时，不阻断聊天回答。
- 模型必须明确说明本轮联网搜索不可用或未命中，不能伪造网页来源。
