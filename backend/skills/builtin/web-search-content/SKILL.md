---
name: web-search-content
display_name: 联网搜索内容
description: 在用户显式开启联网搜索时，使用 Tavily Search API 获取公开网页结果，并把来源上下文交给当前选择的模型。
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

当用户在聊天输入区打开“联网搜索”开关时，Project_R 调用后端配置的 Tavily Search API 获取公开网页结果，保留标题、URL 和摘要，并把这些来源作为上下文交给当前选择的模型。

联网搜索能力应保持模型无关：前端选择 DeepSeek、MiMo 或其他模型时，只要开启联网搜索，都应通过同一搜索上下文链路获得可审计来源。

## 适配模型

- 所有可用聊天模型：默认使用 `WEB_SEARCH_PROVIDER=tavily` 的网页摘要注入方式。

## 处理步骤

1. 用户开启联网搜索后，后端按 `WEB_SEARCH_PROVIDER` 选择搜索链路。
2. 生产默认链路为 `tavily`：调用 Tavily Search API。
3. 搜索取前 5 条结果，保留标题、URL 和摘要。
4. 搜索结果会格式化为 `[来源 N]` 引用块注入模型上下文。
5. 搜索失败或摘要不足时，模型必须明确说明缺口，不能伪造网页来源。

## 搜索 Provider

生产推荐配置：

- `WEB_SEARCH_PROVIDER=tavily`
- `WEB_SEARCH_TIMEOUT_SECONDS=90`
- `TAVILY_BASE_URL=https://api.tavily.com`
- `TAVILY_SEARCH_DEPTH=basic`
- `TAVILY_MAX_RESULTS=5`
- `TAVILY_API_KEY_1`
- `TAVILY_API_KEY_2`

普通搜索 provider 可通过环境变量切换：

- `WEB_SEARCH_PROVIDER=tavily`，需要 `TAVILY_API_KEYS` 或 `TAVILY_API_KEY_1` / `TAVILY_API_KEY_2`
- `WEB_SEARCH_PROVIDER=serper`，需要 `SERPER_API_KEY`
- `WEB_SEARCH_PROVIDER=duckduckgo`
- `WEB_SEARCH_PROVIDER=bing`，需要 `BING_SEARCH_API_KEY`

说明：

- `tavily` 是生产默认路径。
- `duckduckgo` 依赖 HTML 页面解析，只适合作为开发或临时 fallback，不作为生产默认。
- `bing` 仅保留兼容入口，不作为新部署默认方案。
- Tavily API Key 只允许写在后端 `.env`，不得进入前端、日志、响应体或文档示例。

## 错误处理

- 搜索失败或无结果时，不阻断聊天回答。
- 模型必须明确说明本轮联网搜索不可用或未命中，不能伪造网页来源。
