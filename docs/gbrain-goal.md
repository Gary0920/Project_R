目标：在不修改 GBrain 上游源码的前提下，完成 Project_R 对 GBrain 系统能力的产品化适配，重点补齐：关系图谱 UI、客户/项目事件图谱入口、实体合并审核、Dream Cycle 定时维护、真实 citation-fixer 改写型任务、长期 worker、客户工作区权限面板，并完成可重复验证。

工作边界：
1. 不直接修改 `reference/gbrain-master` 上游源码；如发现必须修改，先停止并说明原因，优先用 Project_R adapter、配置、MCP/HTTP、GBrain CLI、GBrain 原生 operation 或 patch 记录方案解决。
2. GBrain 负责 source、sync、query、think、citation、graph、timeline、maintain、jobs、agent/citation-fixer 等后 Markdown 知识库能力。
3. Project_R 负责权限、UI、原始资料保管、extractor、审核、任务编排、通知、审计和管理员操作面板。
4. 不能把客户资料写入 `company-wiki`；客户情报必须使用受限客户情报 GBrain 数据范围。`customer-reference` 只是当前早期实现 source id，不是产品层术语。所有客户信息可在同一客户情报数据范围内共存，不能再按“每个客户一个 GBrain source”设计查询边界。
5. 不要假装完成；每个模块必须有代码、入口、状态展示、失败处理、测试或最小验证。
6. 2026-06-02 用户确认：客户复杂资料提炼（图片、ZIP、Excel、复杂附件等客户样本 extractor）暂时从本 goal 取消，不作为完成条件；当前只要求复杂客户资料不污染 GBrain，继续标记 `pending_extractor_capability`，等待真实样本后另开目标。

第一阶段：现状核对
1. 阅读并更新以下文档作为事实基准：
   - `AGENTS.md`
   - `docs/gbrain-adaptation-progress.md`
   - `docs/gbrain-feature-inventory.md`
   - `docs/gbrain-ingest-workflow.md`
   - `docs/gbrain-agent-citation-fixer-runbook.md`
2. 核对当前 GBrain source 状态：
   - `company-wiki`
   - 受限客户情报数据范围（当前早期实现 source id 为 `customer-reference`）
   - 当前存在的 `project-*` source
3. 运行现有回归：
   - `backend/scripts/gbrain_query_regression.py`
   - `backend/scripts/gbrain_think_regression.py`
   - `backend/scripts/gbrain_customer_reference_regression.py`
4. 若 GBrain 服务、Ollama embedding、DeepSeek Think 或 customer source 不可用，先修复到回归通过，再继续。

第二阶段：关系图谱 UI 与事件图谱入口
1. 调研 GBrain 当前可用 graph/timeline/backlinks/edges/graph-query 相关 MCP operation、CLI 命令和现有 adapter 能力。
2. 在 Project_R 后端新增或完善 GBrain graph/timeline adapter：
   - 按 source scope 查询图谱数据
   - 支持 company/project/customer 三类 source
   - 返回节点、边、来源 citation、时间事件、实体类型、置信度/来源文件
3. 在前端新增入口：
   - 管理员 GBrain 面板中的“图谱 / Timeline”入口
   - 项目工作区中的“项目事件图谱”入口
   - 客户工作区 / 客户情报中的“客户关系网 / 客户画像记忆”入口
4. UI 第一版不追求炫技，优先可用：
   - 节点列表 + 关系边列表
   - 可按人员、公司、项目、事件、source 过滤
   - 点击节点显示来源片段和关联文件
   - 支持从图谱节点跳回 GBrain citation/source preview
5. 增加测试或最小验证，至少用客户情报数据中的 5Points、18 Mary Avenue、Aaron Morris 验证人物、公司、项目关系可展示。

第三阶段：实体增强与实体合并审核
1. 设计 Project_R 侧实体审核模型或复用现有 KnowledgeReview：
   - 疑似重复实体
   - 实体别名
   - 公司/客户/项目关联修正
   - 错误关系删除或降权
2. 后端实现实体候选接口：
   - 从 GBrain graph/timeline/query 结果中提取候选实体
   - 识别同名、近似名、别名、跨文件重复画像
   - 生成待审核项，不自动覆盖事实
3. 前端实现“实体合并审核”面板：
   - 显示实体 A / B 对比
   - 显示来源 citation
   - 支持合并、拒绝、标记别名、保留冲突
4. 审核通过后，Project_R 写入对应 source 的 `derived/` 审核沉淀 Markdown 或 entity override Markdown，再触发 GBrain sync。
5. 增加回归样本，验证实体合并不会污染 `company-wiki`，客户实体只影响客户 source。

第四阶段：Dream Cycle 定时维护
1. 调研 GBrain 原生 dream/maintain/onboard/jobs/autopilot-cycle 能力，优先调用原生命令或 MCP operation。
2. 在 Project_R 后端新增维护计划配置：
   - 手动运行
   - 每日 / 每周定时运行
   - 仅检查模式
   - 允许的维护 job 白名单
   - source scope 限制
   - token/费用/风险提示
3. 接入 Project_R 异步队列或后台 worker：
   - 定时触发 GBrain maintain/dream/check
   - 记录 job id、状态、日志摘要、失败原因
   - 完成后通知管理员
4. 管理员面板展示：
   - 最近维护时间
   - 维护状态
   - 发现的问题
   - 建议动作
   - 可重试/取消
5. 不允许自动无审核改写公司知识。任何事实修改、引用修复、实体合并都必须进入审核或明确的管理员动作。

第五阶段：真实 citation-fixer 改写型任务
1. 使用现有 `docs/gbrain-agent-citation-fixer-runbook.md` 和 adapter，补齐真实 citation-fixer 执行闭环。
2. 准备一个安全测试页，不能使用敏感资料，不能破坏正式知识。
3. 提交 citation-fixer subagent 改写型任务：
   - source scope 必须绑定
   - tools 必须受限
   - slug prefix 必须受限
   - budget 必须受限
4. 验证：
   - job 能创建
   - worker 能执行
   - citation-fixer 能读写目标测试页
   - 修改进入 derived Git 记录或 GBrain 可追踪记录
   - 修改后 query/think citation 有改善
5. 成功后把 `GBRAIN_AGENT_EXECUTION_VERIFIED` 或等价状态更新为真实已验证；如果失败，记录失败原因和下一步，不得标记 ready。

第六阶段：长期 worker
1. 评估当前 PGLite 对长期 worker 的限制；如 GBrain 长期 worker 更适合 Postgres，明确记录。
2. 在 Project_R 中实现或接入 worker 启停/健康检查：
   - worker status
   - job queue status
   - last heartbeat
   - failed jobs
   - restart action
3. 管理员后台显示长期 worker 状态。
4. worker 异常时通知管理员。
5. 至少完成一次真实 job 从 submit 到完成的端到端验证。

第七阶段：客户工作区权限面板
1. 基于现有工作区权限规则完善客户工作区：
   - 系统管理员可进入全部客户工作区
   - 客户工作区管理员只管理该客户工作区
   - 普通用户必须被邀请或属于授权组别
   - 客户 source 默认不可被公司普通员工搜索
2. 后端补齐客户工作区 CRUD / membership / group access；查询统一映射到受限客户情报 GBrain 数据范围，不再新增每客户独立 source mapping。
3. 前端新增客户工作区权限面板：
   - 成员列表
   - 组别授权
   - 工作区管理员设置
   - 邀请/移除成员
   - source 可见性状态
   - 审计记录
4. 客户资料上传后，只能进入受限客户情报 GBrain 数据范围，不得流入 `company-wiki`；当前 goal 只覆盖已支持的文本类客户资料，复杂客户资料提炼暂不纳入验收。
5. 用 `backend/workspace_data/customer/reference` 作为第一轮早期验收样本，后续真实客户工作区仍汇入同一个客户情报数据范围。

第八阶段：质量回归与文档收口
1. 新增或扩展回归脚本：
   - company graph/timeline 回归
   - customer graph/timeline 回归
   - entity merge 审核回归
   - citation-fixer 改写回归
   - dream/maintain job 回归
   - customer permission 回归
2. 至少运行：
   - 后端相关 pytest
   - GBrain query regression
   - GBrain think regression
   - customer intelligence regression
   - 新增 graph/entity/worker/permission 回归
3. 更新：
   - `docs/gbrain-adaptation-progress.md`
   - `docs/gbrain-feature-inventory.md`
   - `docs/gbrain-ingest-workflow.md`
   - 必要时新增 ADR
4. 最终输出必须明确：
   - 已完成模块
   - 未完成模块
   - 风险
   - 验证命令和结果
   - 是否修改 GBrain 上游源码；默认应为没有修改

完成标准：
1. company/project/customer source 都能保持 source scope 隔离。
2. `/query` 继续稳定使用 GBrain Think，不退回旧 RAG。
3. 管理员能在 UI 中看到维护、图谱、实体审核、citation-fixer、worker 状态。
4. 客户工作区权限能防止非授权用户访问客户 source。
5. 至少一个客户关系网和一个项目事件图谱能从真实 source 数据中展示。
6. 至少一次真实 citation-fixer 改写型任务完成验证。
7. 所有新增能力有最小测试或可重复脚本验证。
8. 文档记录真实进度，不夸大完成度。
