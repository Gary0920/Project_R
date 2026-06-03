# GBrain 维护 Worker 策略文档

- 状态：confirmed，2026-06-02
- 适用范围：Project_R 后端维护 worker 的设计决策与运维边界

## 总体决策

Project_R 当前使用 Project_R 自身维护 worker + PGLite inline 执行，**暂缓** GBrain 原生 Postgres worker 长跑。

理由：
- GBrain PGLite 不支持 persistent background worker，只能通过 Project_R 侧线程模拟周期性维护。
- GBrain 原生 Postgres worker 需要单独的 Postgres 实例和 `gbrain serve --worker` 常驻进程，运维复杂度高。
- 当前 PGLite inline 模式已能满足公司 wiki 维护、项目 source 维护和引用修复的 MVP 需求。
- 后续升级到 GBrain 原生 Postgres worker 是性能优化方向，不是功能阻塞项。

## Worker 架构

```text
FastAPI startup
  └── start_gbrain_maintenance_worker()
        ├── Dream Cycle tick (每周期检查到期 + 提交维护任务)
        ├── Dream Cycle poll (轮询已提交的 Dream Cycle jobs)
        ├── Citation-fixer poll (轮询管理员提交的引用修复 jobs)
        └── Contradiction probe tick (每周期检查到期 + 运行冲突探针)
```

## Worker 生命周期

**启动**：FastAPI 启动时自动拉起 daemon 线程，由 `PR_GBRAIN_MAINTENANCE_WORKER_ENABLED` 控制（默认启用）。

**停止**：FastAPI shutdown 事件触发 `stop_gbrain_maintenance_worker()`，设置 stop_event 并等待最多 2 秒让线程退出。

**重启**：管理员通过 API `POST /admin/knowledge/gbrain/dream-cycle/worker/restart` 重启 worker，或修改 `PR_GBRAIN_MAINTENANCE_WORKER_INTERVAL_SECONDS` 后重启。

**状态**：可通过 `GET /admin/knowledge/gbrain/maintenance` 查看 `dream_cycle_worker` 字段，包含 running、enabled、interval_seconds、heartbeat、run_count、last_error 和四个子系统的最近结果。

## 子系统策略

### Dream Cycle（自动维护周期）

| 属性 | 值 |
|---|---|
| 默认启用 | false（需管理员在 GBrain 维护区手动开启） |
| 默认间隔 | 168 小时（7 天） |
| 提交任务 | `autopilot-cycle`（白名单维护 job） |
| 自动提交 | 是（到期时 worker 自动提交，不需要管理员手动触发） |
| 可手动运行 | 是（`POST /admin/knowledge/gbrain/dream-cycle/run?force=true`） |
| 结果写入 | 通知中心 + 审计日志 + `gbrain-dream-cycle.json` manifest |

**安全边界**：Dream Cycle 只提交 GBrain 维护白名单中的 job（sync/embed/lint/backlinks/autopilot-cycle），不包含 `shell` 或任意命令。所有 job 在 PGLite inline 模式下由 GBrain 本地执行器处理。

### Citation-Fixer（引用修复）

| 属性 | 值 |
|---|---|
| 触发方式 | 必须管理员手动提交（`POST /admin/knowledge/gbrain/citation-fixer` 或知识审核页"引用修复"按钮） |
| Worker 自动提交 | **否**（引用修复改写正式 derived Markdown，必须管理员确认） |
| Worker 轮询 | 是（worker 每周期轮询已提交的 tracked jobs，终态完成时同步 sidecar 回正式 derived） |
| 改写范围 | 由 `allowed_slug_prefixes` 限定，默认仅为同目录 slug |
| 回滚能力 | 管理员可以从面板逐个回滚 citation-fixer job 的 Git 提交 |
| 结果写入 | 通知中心 + 审计日志 + `gbrain-citation-fixer-jobs.json` manifest + derived Git 提交 |

**安全边界**：不允许自动无审核改写公司知识。所有 citation-fixer 提交必须管理员手动操作，且限制 slug 前缀和单次 turns 上限。改写完成后不会自动通过关联的知识审核项（review 保持 pending，管理员仍需判断是否驳回/修改/通过）。

### Contradiction Probe（冲突探针）

| 属性 | 值 |
|---|---|
| 默认启用 | false（需管理员在 GBrain 维护区手动开启） |
| 默认间隔 | 168 小时（7 天） |
| Worker 自动运行 | 是（到期时 worker 自动运行，使用配置的查询列表） |
| 执行方式 | GBrain CLI `eval suspected-contradictions run`（会短暂停 HTTP 服务避免 PGLite 锁冲突） |
| 改写能力 | **否**（只读探针，只发现疑似冲突，不自动修任何知识页） |
| 结果写入 | 通知中心 + 审计日志 + `gbrain-contradiction-probe.json` manifest |

**安全边界**：contradiction probe 是只读工具，输出的是疑似冲突列表。管理员必须手动判断并决定是否在现有知识审核流程中处理。探针不会自动创建 review、修改 derived 文件或覆盖 GBrain pages。

## 错误处理

| 场景 | 行为 |
|---|---|
| Worker tick 内部异常 | 写入 `last_error`、通知系统管理员、写入 `gbrain_dream_cycle_worker_error` 审计日志 |
| 单次异常后 | Worker 不停止，下一周期继续尝试 |
| Citation-fixer reconcile 失败 | 通知管理员，tracked job 标记为失败，不阻止其他 job 轮询 |
| Contradiction probe 超时 | 写入超时错误，不阻塞 worker 其他任务 |

## 运维校验清单

管理员可通过 GBrain 维护区 Worker 诊断卡验证以下项：

- [ ] Worker running/enabled 状态
- [ ] Heartbeat 更新正常
- [ ] Dream tick 最新结果
- [ ] Dream poll 最新结果
- [ ] Citation-fixer poll 最新结果
- [ ] Contradiction probe 最新结果
- [ ] 最近错误为空
- [ ] AuditLog 有 `gbrain_dream_cycle_worker_tick` 记录

可通过以下管理操作主动验证：

1. 重启 Worker：`POST /admin/knowledge/gbrain/dream-cycle/worker/restart`
2. 手动运行 Dream Cycle：`POST /admin/knowledge/gbrain/dream-cycle/run?force=true`
3. 手动检查到期：`POST /admin/knowledge/gbrain/dream-cycle/tick`
4. 提交维护任务：`POST /admin/knowledge/gbrain/jobs` (name=sync/embed/lint/backlinks)
5. 提交引用修复：`POST /admin/knowledge/gbrain/citation-fixer`
6. 手动运行冲突探针：`POST /admin/knowledge/gbrain/contradiction-probe/run`

## 后续演进方向

- **GBrain 原生 Postgres worker**（暂缓）：当公司知识库规模达到数千页/chunks 时，PGLite inline 执行可能成为瓶颈，届时评估升级到 Postgres + gbrain serve --worker 常驻模式。
- **批量 citation-fixer 费用/权限边界**（暂缓）：当前逐单提交 + 轮询模式适合 MVP，批量场景需要更细的预算控制和并发限制。
- **自动 remediation 费用/权限边界**（暂缓）：当前所有改写都需要管理员手动确认，后续可能对低风险改写（如纯格式修正）实现自动 remediation，但必须保留审计和回滚。
- **Dream Cycle 运行窗口策略**（暂缓）：当前间隔是全局固定小时数，后续可能增加运行窗口（如仅在工作日凌晨运行）。

## 已知限制

- PGLite 不支持 persistent background worker，需要 Project_R FastAPI 进程存活才能执行维护 tick。
- Contradiction probe 运行时需要短暂停 GBrain HTTP 服务（PGLite 不支持并发写），期间 `/query` 请求会返回 503。
- Dream Cycle 默认间隔 168 小时，如果管理员忘记手动检查到期，首次要等一周。
- Worker 是 FastAPI 进程内线程，如果 FastAPI 进程被 SIGKILL 杀掉，worker 不会优雅退出。
- 没有 GUI 直接控制 worker 的 enable/disable（需修改环境变量或代码配置），这是有意为之——worker 是后端基础设施，不应频繁开关。

## 相关文档

| 文件 | 用途 |
|---|---|
| `backend/core/gbrain_maintenance_worker.py` | Worker 线程、启停、状态和周期执行 |
| `backend/core/gbrain_dream_cycle.py` | Dream Cycle 计划、提交、轮询 |
| `backend/core/gbrain_citation_fixer_jobs.py` | Citation-fixer job 追踪、轮询、sidecar 同步、回滚 |
| `backend/core/gbrain_contradiction_probe.py` | 冲突探针配置、运行、调度 |
| `backend/api/rag.py` | 管理员 API：worker restart、dream cycle CRUD、citation-fixer、contradiction probe |
| `docs/adr/0003-gbrain-service-adapter.md` | Project_R 通过 GBrain HTTP/MCP adapter 调用 GBrain |
| `docs/gbrain-agent-citation-fixer-runbook.md` | Citation-fixer 的 OAuth、gateway loop、预检和执行流程 |
| `patches/gbrain/` | GBrain 上游本地 patch 集合 |
