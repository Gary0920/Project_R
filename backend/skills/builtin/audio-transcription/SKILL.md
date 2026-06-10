---
name: audio-transcription
display_name: 录音转文字
description: 将会议录音、音频或视频文件转录为文字稿。需要上传或引用一个音频/视频文件。支持 MP3、WAV、M4A、OGG、FLAC、MP4、MOV 等格式。转录结果以文字形式返回，不会自动保存到项目文件或录入 GBrain。
category: 综合
priority: medium
trigger:
  - 录音转文字
  - 音频转录
  - 音频转文字
  - 语音转文字
  - 会议录音转录
  - 将这段录音转录成文字
  - 把这段音频转文字
  - audio-transcription
  - transcribe audio
inputs:
  - name: audio_source
    type: file
    label: 音频或视频文件
    required: true
outputs:
  - type: chat_text
    format: plain_text
governance:
  risk_level: medium
  requires_confirmation: false
  mutates_source_files: false
  triggers_gbrain_sync: false
  allowed_tools: []
---

# 录音转文字 (Audio Transcription)

## Purpose

将用户附件中的音频/视频文件转录为文字稿。本 Skill 会调用 MiMo V2.5 模型进行语音识别，并将结果以文字形式返回给用户。

## Trigger Conditions

- 用户输入匹配「录音转文字」「音频转录」「transcribe audio」等关键词。
- 用户在附件中上传了音频或视频文件。

## Processing Rules

1. 检查当前会话是否有音频/视频附件（MP3/WAV/M4A/OGG/FLAC/MP4/MOV）。
2. 如果没有附件，回复要求用户上传或引用音频文件。
3. 如果有多个音频文件，只处理第一个，其余忽略。
4. 调用 `core.media_transcription.transcribe_media_to_markdown()` 进行转录。
5. 转录结果以文字形式返回，不自动保存到项目文件。
6. 不触发 GBrain sync，不写入 `_preprocessed/gbrain-ready/`。
7. 使用 MiMo V2.5 模型（与会议音视频预处理同一链路），不使用 MiMo V2.5 Pro。

## Non-Goals

- 不通过普通 Chat 自动理解音频内容。
- 不自动保存转录结果到项目文件。
- 不自动录入 GBrain。
- 不修改源文件。
