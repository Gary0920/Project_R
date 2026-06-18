# Project_R 开发流程 V2.3：联网搜索升级任务计划

## 1. 结论

联网搜索升级采用 **Tavily Search API 主路径**。

已取消：

- 自托管 SearXNG 部署路线。
- DeepSeek native web_search 路线。
- DuckDuckGo HTML 解析作为默认 fallback。

用户在前端选择任意聊天模型并打开“联网搜索”后，后端调用 Tavily Search API 获取公开网页结果，再把标题、URL 和摘要作为来源上下文交给当前选择的模型。搜索能力与模型 provider 解耦，前端不接触 API Key。

## 2. 目标行为

用户开启“联网搜索”后：

1. 后端读取 `WEB_SEARCH_PROVIDER`。
2. 生产默认配置为 `WEB_SEARCH_PROVIDER=tavily`。
3. 后端调用 `search_web()`，通过 Tavily `/search` API 获取网页结果。
4. 搜索结果取前 5 条，过滤空标题、空 URL 和重复 URL。
5. 结果格式化为 `[来源 N]` 引用块，注入当前模型上下文。
6. 返回给前端的消息包含：
   - assistant 文本。
   - `sources_json` 来源。
   - `context_trace.web_search` 调用轨迹。
7. `web_search=False` 时不得触发搜索 provider。
8. 未配置 Tavily Key 时，后端返回可审计 warning，不伪造结果，不降级到 DuckDuckGo。

## 3. 推荐配置

真实配置写入 `backend/.env`：

```env
WEB_SEARCH_PROVIDER=tavily
WEB_SEARCH_TIMEOUT_SECONDS=90
TAVILY_BASE_URL=https://api.tavily.com
TAVILY_SEARCH_DEPTH=basic
TAVILY_MAX_RESULTS=5
TAVILY_API_KEY_1=tvly-你的第一个key
TAVILY_API_KEY_2=tvly-你的第二个key
```

也可以使用逗号写法：

```env
TAVILY_API_KEYS=tvly-你的第一个key,tvly-你的第二个key
```

约束：

- 真实 Tavily Key 只允许存在于 `backend/.env`。
- Key 不进入前端、日志、响应体、文档示例或 Git。
- 多 Key 使用后端轮询，避免前端感知 Key。

## 4. 文件变更

### 4.1 `backend/app/shared/web_search/service.py`

目标：新增 `tavily` provider。

任务：

- 支持 `WEB_SEARCH_PROVIDER=tavily`。
- 使用 `POST https://api.tavily.com/search`。
- Header 使用 `Authorization: Bearer <key>`。
- 请求体显式设置：
  - `query`
  - `search_depth`
  - `max_results`
  - `include_answer=false`
  - `include_raw_content=false`
- 解析 `results[].title`、`results[].url`、`results[].content`。
- 支持：
  - `TAVILY_API_KEYS`
  - `TAVILY_API_KEY`
  - `TAVILY_API_KEY_1`
  - `TAVILY_API_KEY_2`
- 多 Key 轮询。
- 未配置 key 时返回 `missing_tavily_api_key` warning。

### 4.2 `backend/.env.example`

目标：提供非敏感配置模板。

任务：

- 默认 `WEB_SEARCH_PROVIDER=tavily`。
- 提供 `TAVILY_API_KEY_1` / `TAVILY_API_KEY_2` 空位。
- 不写真实 key。

### 4.3 `backend/skills/builtin/web-search-content/SKILL.md`

目标：同步业务 Skill 文档。

任务：

- 明确 Tavily 是生产默认 provider。
- 移除 SearXNG 与 DeepSeek native 作为推荐路径。
- 保留失败时不能伪造网络来源的规则。

### 4.4 `docs/operations/WINDOWS_SETUP.md`

目标：说明 Windows 本地如何填写 Tavily Key。

任务：

- 移除 Docker / SearXNG 运维步骤。
- 说明两个 Tavily Key 的填写位置。

### 4.5 `backend/tests/`

目标：用 mock 测试覆盖 Tavily provider。

任务：

- 新增 `backend/tests/test_web_search_tavily.py`。
- 覆盖 Tavily 响应解析。
- 覆盖缺 Key warning。
- 覆盖两个 Key 轮询。
- 保留 Chat 层普通联网搜索测试。

## 5. 验证命令

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest tests/test_web_search_tavily.py tests/test_chat_phase6.py
```

## 6. 验收标准

- [ ] `.env.example` 默认 `WEB_SEARCH_PROVIDER=tavily`。
- [ ] `backend/.env` 可填写两个 Tavily Key。
- [ ] `WEB_SEARCH_PROVIDER=tavily` 时，`search_web()` 可解析 mock Tavily JSON 结果。
- [ ] 未配置 Tavily Key 时返回 `missing_tavily_api_key`。
- [ ] 两个 Tavily Key 可轮询。
- [ ] Chat 开启 `web_search=True` 时仍走普通搜索上下文注入。
- [ ] Chat 关闭 `web_search=False` 时不触发搜索。
- [ ] SearXNG 部署脚本和 Docker 文档已移除。
- [ ] 相关 pytest 使用项目虚拟环境运行并通过。

## 7. 后续增强

- 管理员健康检查展示 Tavily provider 状态。
- 前端来源区域显示搜索 provider。
- 根据业务需求增加 Tavily `topic`、时间范围、domain include/exclude。
