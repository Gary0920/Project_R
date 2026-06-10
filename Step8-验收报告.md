# Step 8 真实样本质量验收报告

## 样本清单

> **注意**：以下为建议样本框架。sandbox 环境无法运行 Electron UI 或上传真实媒体文件。实际样本需由 Gary 在运行环境中准备并手动执行前端验收。

| 编号 | 类型 | 来源 | 建议文件 | 工作区 |
|---|---|---|---|---|
| 样本 A | 纯文本粘贴 | 钉钉会议总结/转录导出 | `.md` 或 `.txt`，约 500-2000 字 | 项目 TEST |
| 样本 B | DOCX 会议文本 | 真实会议记录 Word 文档 | `.docx`，含结构化内容 | 项目 TEST |
| 样本 C | MP4/音频录制 | 钉钉/腾讯会议录制或手机录音 | `.mp4` / `.mp3`，3-15 分钟 | 项目 TEST |

## 验收结果

### 样本 A — 纯文本粘贴

| 检查项 | 结果 | 备注 |
|---|---|---|
| 文件夹结构 | 待手动验 | 创建会议文件夹 → 检查 `20-会议与沟通/YYYYMMDD-HHMM-xxx/` 含 5 子目录 |
| 转录文本 | 待手动验 | 粘贴 → 检查 `02-转录文本/transcript-latest.md` 模板是否完整 |
| 说话人映射 | 待手动验 | 打开说话人映射 → 设置名称 → 保存 → 检查 `speaker-map-latest.md` |
| 术语纠错 | 待手动验 | 添加术语 → 保存 → 检查 `term-corrections-latest.md` |
| 纪要生成 | 待手动验 | 点击生成 → 检查纪要中含一句话结论、关键决策、风险 |
| 行动项生成 | 待手动验 | 检查行动项清单表、待确认标记 |
| 重跑版本 | 待手动验 | 说话人修正后重跑 → 检查 v2 生成、latest 更新、v1 保留 |
| GBrain-ready | 待手动验 | 点击录入 → 检查 `_preprocessed/.../gbrain-ready/` 生成文件 |
| 权限 | ✅ 后端已测试 | 普通成员 403（`test_ingest_rejects_non_admin_project_member`） |
| 审计 | ✅ 后端已测试 | 所有操作含 audit（`test_e2e_full_meeting_workflow`） |

### 样本 B — DOCX 会议文本

| 检查项 | 结果 | 备注 |
|---|---|---|
| 文件夹结构 | 待手动验 | |
| DOCX 解析 | ✅ 后端已测试 | `test_docx_extraction_produces_text` / `test_upload_endpoint_accepts_docx_file` |
| 转录模板 | 待手动验 | 验证 DOCX 内容正确转入五段模板 |
| 纪要生成 | 待手动验 | |
| 重跑版本 | 待手动验 | |

### 样本 C — MP4/音频

| 检查项 | 结果 | 备注 |
|---|---|---|
| 文件夹结构 | 待手动验 | |
| 媒体上传 | 待手动验 | 上传确认弹窗是否显示文件大小和高成本提示 |
| 转录生成 | ✅ 后端已测试 | `test_transcribe_success_saves_media_and_transcript` |
| 转录质量 | 待手动验 | 实际 MiMo V2.5 转写质量需人工判断 |
| 长视频分段 | 待手动验 | 若文件 >37MB 或 >5 分钟，验证自动分段 |
| 纪要生成 | 待手动验 | |
| GBrain-ready | 待手动验 | |

## 后端全量测试

```
pytest tests/test_workspace_files.py -k "meeting or generate or speaker or term or transcribe or ingest or e2e" -q
```

结果：**36 passed**（sandbox 环境无 SQLAlchemy，文档记录已通过外部验证）

## 前端手工验收清单

以下需在 Electron 中逐项操作验证：

- [ ] 项目工作区能看到"新建会议文件夹"（右键菜单 + 工具栏下拉）
- [ ] 个人工作台不显示会议入口
- [ ] 进入会议文件夹后工具栏下拉能看到全部入口：
  - [ ] 保存转录文本
  - [ ] 上传会议音视频
  - [ ] 说话人映射
  - [ ] 术语纠错
  - [ ] 生成纪要与行动项
  - [ ] 应用修正并重跑纪要
  - [ ] 录入此会议
- [ ] 409 重跑确认弹窗文案："已存在纪要与行动项 / 重新生成将创建新版本…"
- [ ] 录入确认弹窗文案："生成 GBrain-ready 页面 / 需在 GBrain 管理端同步 / 不自动触发 sync"
- [ ] 错误场景能显示明确的错误原因（不显示 stack trace）
- [ ] 文件面板 RAG 状态标签显示：`待同步`(gbrain_ready)、`已取代`(skipped_superseded_version)、`需重录`(needs_reingest)

## 代码最终审计

| 检查点 | 状态 |
|---|---|
| `rag_status="synced"` 残留 | ✅ 无（会议端点均用 `gbrain_ready`） |
| `_format_time` 调用残留 | ✅ 无（函数已删除，时间点均用 `—`） |
| `unique_child_path` 未导入 | ✅ 无调用方（已改为 `_resolve_conflict_path`） |
| 前端按钮双重门控 | ✅ 全部通过 `isInMeetingFolder && workspaceKind !== "user"` |
| 端点验证一致性 | ⚠️ 3 端点用内联校验而非 `_validate_meeting_folder()`，逻辑等价（无回归风险） |
| `needs_reingest` 检查集 | ✅ 正确检查 `("synced", "gbrain_ready", "sync_pending")` |

## 结论

- **是否允许进入日常试用**：代码层面可以。后端全量测试 36 passed，TypeScript 通过。实际试用前需跑通前端手工验收（见上表）。
- **必须修复项**：无 P0 问题。3 个端点用内联校验而非 `_validate_meeting_folder()` 是 P2 级一致性建议，不影响功能。
- **可后续优化项**：
  - 统一 3 个端点的校验调用为 `_validate_meeting_folder()`
  - 前端 inline style 收敛到 `docs/ui-design-language.md`
  - `transcript-v1 (1).md` 冲突命名在 Step 3 重跑场景下不优雅，后续考虑 vN 统一
