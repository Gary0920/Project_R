---
name: meeting-audio-video-preprocess
display_name: 会议音视频转写与结构化提炼
description: Transcribe meeting audio/video when needed, then extract bilingual structured meeting Markdown with decisions, action items, risks, evidence, and review notes. Use when preprocessing `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`, `.flac`, `.mp4`, `.mov`, `.mkv`, or `.webm` meeting media before writing to `_preprocessed/.../gbrain-ready/`.
category: 资料预处理
priority: high
trigger:
  - meeting-audio-video-preprocess
  - 会议音视频预处理
  - 会议录音录入
  - 会议视频录入
  - transcript 结构化
inputs:
  - name: source_path
    type: path
    label: 会议音频或视频
    required: true
  - name: source_scope
    type: select
    label: Source scope
    required: true
    options: [company, project, customer]
  - name: source_id
    type: text
    label: GBrain source id
    required: true
outputs:
  - type: file
    format: markdown
execution:
  mode: transcription_then_structured_preprocess
  script: backend/scripts/preprocess_meeting_audio_video_source.py
  core_modules:
    - core.media_transcription
    - core.meeting_structured_extraction
  model_profile: mimo-v2-5
governance:
  risk_level: high
  requires_confirmation: true
  mutates_source_files: false
  triggers_gbrain_sync: false
---

# 会议音视频转写与结构化提炼

## Purpose

把会议音频/视频或已有 transcript sidecar 提炼成 GBrain-ready Markdown。此 Skill 的顺序是：先获得 transcript，再从 transcript 中结构化提取决策、行动项、风险、证据和待审核问题。

## Trigger Conditions

- 用户或管理员显式触发“录入”或“录入此文件”。
- 源文件为会议音频/视频，或同名目录/sidecar 中已有 `.transcript.*`、`.vtt`、`.srt`、`.json` transcript。
- 文件内容是项目会议、客户会议、现场会议、复盘会、培训或内部分享。

## Non-Goals

- 不根据音视频直接生成最终结论而跳过 transcript。
- 不编造说话人、行动项、决策或风险。
- 不使用 MiMo V2.5 Pro。
- 不自动运行 GBrain sync、Entity Enrichment、graph merge、timeline rebuild、citation-fixer 或 contradiction probe。

## Processing Rules

1. 如果存在 transcript sidecar，优先使用 sidecar。
2. 如果没有 transcript 且用户确认高成本转写，调用 MiMo V2.5 转写；长音视频按配置分段。
3. 转写后可用 DeepSeek profile 做说话人/术语纠错，但不得新增事实。
4. 结构化提炼输出中英双语对齐 Markdown，包含决策、行动项、风险/待确认、时间戳片段和 transcript excerpt。
5. 公司全局会议默认 pending review；项目会议可按项目 source policy 写入项目 source，但保留 review status 和转写来源。

## Output Contract

Frontmatter 必须记录 `preprocess_skill=meeting-audio-video-preprocess`、`preprocess_version`、`prompt_version`、原始媒体路径/hash、transcript 文件、转写状态、segment/action/decision/risk 计数、模型和 token usage。

## Verification

- 单元测试应覆盖 transcript sidecar 路径、无 transcript pending 状态、自动转写生成 sidecar、项目 source 写入 frontmatter。
- 质量样板建议放在 `reference/meeting-audio-video-preprocess/`，至少包含短录音、长视频、已有 transcript 和低质量音频各 1 个。
