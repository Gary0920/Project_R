# Project_R 清理清单报告 - 2026-06-04

## 本次已执行清理

- 已删除 `backend/app.db` 中全部 BFI project 工作区记录：清理前 35 个，清理后 0 个。
- 已删除 `backend/workspace_data/project/BFI/` 下全部工作区子目录，并保留 `BFI/` 品牌根目录。
- 已保留用户表中的 `sysadmin`、`test001`、`test002`，未删除、未禁用、未改角色、未改昵称。
- 已从 `backend/workspace_data/global/company-wiki/manifests/gbrain-think-source-clients.json` 移除 `project-bfi-1` Think client。
- 已用 GBrain CLI 撤销 `project-bfi-1` OAuth client，并永久删除 stale source `project-bfi-1`；`company-wiki`、`customer-reference` 和客户 source 未删除。

## 必须保留

- `backend/app.db`：当前本机真实开发数据库，包含用户、会话、工作区、管理员审计等运行态记录；后续测试不得直接污染。
- `backend/workspace_data/global/company-wiki/`：正式公司知识库 raw/derived/manifests 与 GBrain PGLite home。
- `backend/workspace_data/customer/`：客户情报/画像 source 数据，当前包含 `customer-reference` 和 Lucerna 相关客户资料。
- `backend/workspace_data/user/`：用户默认工作台目录；本次确认 `sysadmin`、`test001`、`test002` 均保留。
- `backend/tests/`：自动化测试资产，当前约 97 个文件，属于必要回归保护。
- `backend/scripts/gbrain_*`、`backend/scripts/clean_notion_markdown_once.py` 等脚本：当前 GBrain 初始化、回归、agent/citation-fixer smoke 和一次性清洗仍有运维价值。
- `docs/adr/`、`docs/gbrain-*.md`、`docs/ui-design-language.md`：当前架构与产品决策依据。

## 可清理但需确认

- `backend/workspace_data/_backups/`：约 503 个文件、约 1.21GB，主要是历史 GBrain reset/测试数据备份；删除前需确认不再需要回滚。
- `backend/knowledge_base/`：约 1146 个文件、约 50MB；AGENTS 已说明旧 RAG/wiki 主路径退役，但目录仍在，删除前需确认没有历史资料要迁移。
- `backend/vector_store/`：约 7 个文件、约 6.56MB；旧 Chroma/vector_store 主路径已退役，删除前需确认没有调试对照价值。
- `backend/workspace_data/project/` 下未来新出现的测试项目：必须先核对 DB、GBrain source 和用户授权，再清理。
- `reference/gbrain-master/`：外部上游源码与本地 patch 验证环境，不属于普通清理对象；升级或缩减前必须审计 `patches/gbrain/`。
- 当前工作树未提交/未跟踪文件：`.gitignore`、`backend/core/gbrain/__init__.py`、前端若干组件/CSS、`scripts/project-r-launcher.ps1`、`.mcp.json`、`.reasonix/`、`JumpBar.tsx`；本次未判断其业务必要性，不应自动删除。

## 明显缓存或临时产物

- `backend/.pytest_cache/`：约 5 个文件、约 38KB，可在不运行测试时清理。
- `backend/__pycache__/`：约 1 个文件、约 4KB，可清理。
- `backend/logs/`：约 15 个文件、约 100KB，可按保留周期清理；若排障正在进行则保留最近日志。
- `backend/session_attachments/`：当前约 1 个文件、18B；属于会话临时附件区域，按既有保留策略清理，不应手工混入公司/项目知识库。
- `backend/generated_files/`：当前为空；后续由生成文件过期清理策略治理。

## 后续建议

- 增加一个只读 `scripts/audit_runtime_data.py` 或管理员诊断入口，用于列出 DB 工作区、磁盘目录、GBrain source/client 的不一致项。
- 改进 `DELETE /workspaces/{id}` 或新增管理员清理接口：删除工作区时同步处理 DB 关联、磁盘目录、项目 GBrain source、Think client 和审计日志。
- 将测试默认 DB 和 workspace root 固定到临时目录，禁止单元测试直接使用 `backend/app.db` 与正式 `workspace_data/`。
