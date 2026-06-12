# Project_R Windows 全链路联调记录

本文档仅保留 Phase 17 Windows 联调的历史记录与说明。当前正式验收入口以以下文件为准：

- `docs/milestones/Project_R 开发流程.md`
- `docs/validation/electron-manual-checklist.md`
- 自动化检查：后端 `python -m unittest discover -s tests`，前端 `bun run build`

## 2026-05-21 代码级检查

状态：部分完成，真实 Electron 端到端链路待 Gary 手工运行。

已完成：

- 新增 `scripts/test-windows.ps1`，用于检查源码中是否存在 Windows 绝对路径硬编码。
- 检查 `frontend/src` 中是否存在 `localhost` 或 `127.0.0.1` 后端地址硬编码。
- 检查前端默认后端地址是否仍由 `VITE_DEFAULT_API_BASE_URL` 与 `server-atoms.ts` 管理。
- 修复 `scripts/refresh-knowledge.ps1` 登录后读取 token 字段的兼容问题。

本次验证命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test-windows.ps1 -StaticOnly
cd frontend
bun run build
```

待人工补齐：

- 同时启动后端与 Electron 前端。
- 使用管理员账号完成：登录 -> Chat -> /query 知识库问答 -> 手动选择 U03 Skill 并补参生成文件 -> 管理员后台 -> 知识审核。当前显式路由阶段，普通自然语言文件生成入口待后续补齐。
- 按 `docs/validation/electron-manual-checklist.md` 记录关键截图、耗时、失败点和修复结论。

## Phase 16 说明

钉钉 Bot 集成已按 Gary 2026-05-21 决策调整为后补功能。当前阶段只保留设置页中的本地配置占位，不作为 Phase 15/17 验收阻塞项。
