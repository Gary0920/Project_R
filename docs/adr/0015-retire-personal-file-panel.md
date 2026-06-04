# ADR 0015: Retire Personal File Panel

Project_R will keep `{username}的工作台` as the user's personal conversation entry, but will retire the personal file panel as a product line. Personal context is expressed through user-defined prompts, session prompts, current-message attachments, and explicit references; long-term personal file storage remains the user's local filesystem, while governed business files belong in project/customer workspaces.

## Status

Accepted

## Context

The previous personal workspace design included a right-side personal file panel, `常用文件`, `对话文件`, export/download-to-workbench flows, personal recycle-bin behavior, and a 30-day personal-file cleanup strategy. Gary confirmed on 2026-06-04 that once the personal workspace is only a personal context entry, these file-management features add a second personal file system without enough product value.

## Decision

- `{username}的工作台` remains visible and pinned as the user's personal chat/home entry.
- The personal workspace no longer has a right-side personal file panel.
- Project_R no longer provides product flows for `导出到工作台`, `下载到工作台`, personal `常用文件`, personal `对话文件`, personal file recycle-bin governance, or personal 30-day file cleanup.
- Session attachments remain supported as current-conversation context, with technical temporary storage and cleanup as needed, but they are not presented as personal files.
- The personal workspace may run lightweight business Skill / Agent generation tasks, such as drafting, rewriting, filling templates, or generating downloadable files from current-turn inputs, session attachments, explicitly selected local files, or user-filled fields.
- Lightweight personal-workspace Skill / Agent outputs are shown as current-turn results only. They may offer copy and local download/save actions; `download` and `save as local file` are one product concept.
- Lightweight personal-workspace Skill / Agent runs must not perform GBrain ingest, long-term material organization, project/customer source governance, personal file-library governance, project retrospectives, customer profiling, graph entity merge, or knowledge review.
- The personal workspace must not provide cross-workspace actions to save generated outputs, session attachments, or selected local files into project/customer materials. Project-related work should happen inside a project workspace; customer-related work should happen inside a customer workspace.
- Project/customer file panels remain in scope for shared or source-scoped business materials.
- Business files that need long-term retention, sharing, permission governance, audit, ingest, review, retrospective use, or project/customer knowledge citation must live in project/customer workspaces, not in the personal workspace.
- `workspace_data/user/{username}` may remain during migration as a compatibility or temporary attachment path, but it is not a long-term product knowledge source and should be retired once attachment/export/download flows no longer depend on it.

## Consequences

- The UI becomes simpler: personal workspace is for conversation and prompts; file management is reserved for project/customer materials.
- Useful one-off business generation remains available from the personal workspace without recreating a personal file library, personal GBrain source, or cross-workspace save flow.
- User preference and personal working style should be handled through prompt features, not through a personal file library.
- Existing frontend/backend code that assumes a personal file panel must be migrated before deleting `workspace_data/user/`.
