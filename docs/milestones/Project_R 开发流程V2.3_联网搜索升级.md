结论：联网搜索方案建议做成 **DeepSeek 原生 Web Search 首选 + 现有搜索 provider 兜底**。前端“联网搜索”按钮语义不变，后端在开启后优先走 DeepSeek Anthropic Messages 接口，让 DeepSeek 自己调用 `web_search`，再把返回的搜索结果整理进 Project_R 的来源与审计链路。

**目标行为**

用户开启“联网搜索”后：

1. 后端判断 `WEB_SEARCH_PROVIDER=deepseek_native`。
2. 当前模型若为 DeepSeek，则走 `https://api.deepseek.com/anthropic/v1/messages`。
3. 请求携带：

```json
{
  "tools": [
    { "type": "web_search_20250305", "name": "web_search", "max_uses": 3 }
  ]
}
```

4. DeepSeek 自行决定搜索，返回 `server_tool_use`、`web_search_tool_result` 和最终回答。
5. Project_R 解析搜索结果标题、URL、最终回答、usage。
6. UI 继续显示回答，并在消息来源中展示联网来源。
7. 如果 DeepSeek native 搜索失败，再降级到现有 `search_web()` provider。

**建议配置**

新增环境变量：

```env
WEB_SEARCH_PROVIDER=deepseek_native
WEB_SEARCH_DEEPSEEK_MAX_USES=3
WEB_SEARCH_DEEPSEEK_MODEL_PROFILE=deepseek-flash
WEB_SEARCH_FALLBACK_PROVIDER=duckduckgo
WEB_SEARCH_TIMEOUT_SECONDS=90
```

说明：

- `WEB_SEARCH_PROVIDER=deepseek_native`：启用 DeepSeek 原生搜索。
- `WEB_SEARCH_DEEPSEEK_MAX_USES=3`：限制每轮最多搜索次数，控制 token 成本。
- `WEB_SEARCH_DEEPSEEK_MODEL_PROFILE`：联网搜索优先使用的模型 profile。Flash 已验证可用；Pro 更稳但成本更高。
- `WEB_SEARCH_FALLBACK_PROVIDER`：DeepSeek native 失败后的兜底 provider。

**文件变更清单**

1. `backend/app/shared/llm/client.py`  
   新增 DeepSeek Anthropic-compatible Messages 调用能力。  
   主要新增：
   - `DeepSeekAnthropicMessagesClient` 或独立方法
   - 支持 `tools=[web_search]`
   - 解析 `content` block
   - 提取 `web_search_tool_result`
   - 提取 `usage.server_tool_use.web_search_requests`

2. `backend/app/shared/web_search/service.py`  
   保留现有 `duckduckgo / serper / bing` 结构，但新增 `deepseek_native` 的识别。  
   注意：`deepseek_native` 不适合像 DuckDuckGo 那样“先搜索再返回摘要”，它应走 LLM 完整生成链路，所以这里更适合只提供 provider 判断、fallback 和通用 source 转换工具。

3. `backend/app/features/chat/send_message_service.py`  
   调整联网搜索分支：
   - 如果 `WEB_SEARCH_PROVIDER=deepseek_native` 且本轮 `web_search=True`，跳过当前 `maybe_run_web_search()` 的预搜索注入方式。
   - 改为调用 DeepSeek native web search completion。
   - 将返回的 search results 写入 `sources_json`。
   - 将 `context_trace.web_search` 记录为 native provider。

4. `backend/app/features/chat/web_search_context.py`  
   增加 native trace 结构，例如：

```json
{
  "skill_name": "web-search-content",
  "provider": "deepseek_native",
  "native": true,
  "web_search_requests": 1,
  "result_count": 10,
  "fallback_used": false
}
```

5. `backend/skills/builtin/web-search-content/SKILL.md`  
   更新 Skill 文档：
   - 默认推荐 `deepseek_native`
   - 说明 DeepSeek 原生搜索会产生额外 token 费用
   - 说明 fallback provider
   - 删除或弱化 Bing，因为 Bing Search API 已退役，不适合作为新默认方案

6. `backend/.env.example`  
   增加联网搜索配置示例，不写真实 key。

7. `backend/tests/`  
   新增或扩展测试：
   - DeepSeek native 响应解析测试
   - `web_search_tool_result` 转 sources 测试
   - native 搜索失败后 fallback 测试
   - `web_search=False` 时不触发 native 工具测试
   - 不使用真实 DeepSeek API，全部 mock HTTP 响应

**实现优先级**

第一步，MVP：

- 打通 `WEB_SEARCH_PROVIDER=deepseek_native`
- 非流式聊天先支持
- 解析来源并入库
- 失败时明确降级或报 trace
- 跑后端相关 pytest

第二步，体验补强：

- 前端来源区域显示“DeepSeek 原生联网搜索”
- 后台健康检查显示 provider 状态
- 管理员可看到是否缺 Key、是否调用过 web search

第三步，再考虑流式：

- 当前 native web search 会出现工具调用等待期，流式处理要解析 `server_tool_use` 和 `web_search_tool_result` 事件。
- 建议先不动流式，避免一次改动过大。

**关键取舍**

推荐先做非流式 native web search，因为这条链路最短、风险最小，也能直接解决你当前“联网搜索不工作”的问题。

不建议继续把 DuckDuckGo 当生产默认。它在国内网络和 HTML 解析上都不稳定，不适合作为 Project_R 面向中国大陆用户的主要搜索能力。