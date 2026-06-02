# ADR 0013: Personal Workspace and Explicit Local File Selection

Date: 2026-06-02

## Status

Accepted

## Context

ADR 0012 defined the default private workspace as a fixed local-first folder under the user's computer, with Electron metadata tracking that root. During product review, Gary clarified that this created unnecessary conceptual overlap:

- Users already choose files manually from their own computer, so Project_R does not need to force those files into a fixed local private folder first.
- The Project_R right-side file panel also showed a user-scoped server area named like a private space, which made it unclear whether "private space" meant local files or server-held personal files.
- The earlier boundary made the feature look like a personal knowledge base or local workspace, even though the intended need is simpler: temporary personal material, drafts, and explicit handoff into Project_R tasks.

## Decision

Project_R no longer treats a fixed local private workspace root as the product authority.

- The server-side user-scoped area is named `{username}的工作台` in the UI and is called the personal workspace in domain language. The username is automatically derived from the logged-in user.
- The personal workspace uses the same central conversation area as project workspaces, including sessions, Chat / Agent stance, input box, attachments, references, exports, and message bubbles. The main differences are in the right-side file panel, knowledge entry points, permissions, and file governance.
- The personal workspace does not have member management, hidden/open state, or workspace administrator roles. It belongs only to the logged-in user.
- The personal workspace stores files and drafts that the user has already explicitly handed to Project_R, such as conversation attachments, commonly used files, generated drafts, and temporary processing results.
- New users receive a default personal file scaffold with two first-level folders: `常用文件` and `对话文件`. This scaffold is created only when the personal workspace is first created; it is not an immutable system taxonomy.
- Users may create, rename, and delete folders inside their personal workspace file area according to their own habits. Project_R must not recreate renamed or deleted default personal folders during later refresh, login, or path validation.
- `常用文件` stores user-saved personal materials that may be reused frequently, such as templates, reference sheets, descriptions, images, logos, and files the user often wants AI to reference.
- For new users, `常用文件` initially contains four default subfolders: `模板`, `参考资料`, `图片素材`, and `其他`. These subfolders are also only initial scaffolding and remain user-editable.
- `对话文件` stores files tied to a specific conversation for quick reuse, such as conversation attachments, AI-generated files, exported chat Word documents, exported chat PNG images, exported chat PDFs, and temporary drafts. It is not a long-term storage location.
- When Project_R writes conversation-related files into `对话文件`, it creates a conversation folder by default. The folder name should include the date and conversation title, for example `2026-06-02 新会话标题`.
- Each generated conversation folder contains three default subfolders: `附件`, `导出`, and `生成文件`.
- `附件` stores files uploaded or sent for processing in that conversation. `导出` stores exported chat Word, PNG, and PDF files. `生成文件` stores AI-generated documents, spreadsheets, images, or other deliverables from that conversation.
- Files in the personal workspace have a 100MB per-file size limit. Files above this limit should not be accepted into the personal workspace; the UI should direct users to project files or another dedicated path when appropriate.
- Conversation files are not deleted immediately when a conversation ends. User-exported chat files and AI-generated deliverables should remain available unless the user deletes them or runs an explicit cleanup flow.
- Deleting a personal workspace conversation deletes only the conversation record by default. Its corresponding `对话文件` continue to follow the 30-day cleanup strategy.
- Conversation deletion may offer an optional "同时移入回收站" action for related conversation files, but that must not be the default behavior.
- Project_R should provide a 30-day cleanup strategy for stale conversation attachments, chat export files, AI-generated files, temporary drafts, and cleanable caches in the personal workspace.
- `常用文件` is excluded from the 30-day cleanup strategy by default.
- The 30-day cleanup strategy applies by default to conversation-related files, including conversation attachments, exported files, generated files, temporary drafts, processing caches, and generated intermediate files that the user has not explicitly kept. Cleanup governance should rely on file source/purpose metadata, not only on whether the user keeps a literal folder named `对话文件`.
- The 30-day clock starts from the file's latest Project_R usage, including opening, calling, referencing, sending, or using the file in a generation task. If the user uses the file again during the period, the 30-day clock resets from that new latest usage date.
- Project_R should start reminding the user 3 days before the cleanup deadline and continue reminding once per day during the reminder window.
- If the user does not delete, keep, or use the file again by day 30, Project_R moves the file into that workspace's own `.trash` recycle bin instead of permanently deleting it.
- Files in a workspace `.trash` recycle bin remain restorable for another 30 days. If no user restores the file during that period, Project_R may purge the file after the recycle-bin retention window ends.
- Every workspace keeps its own `.trash` recycle bin. The `.trash` folder appears in the normal file directory as a special recycle-bin entry; clicking it opens the recycle-bin view for users who can access that workspace.
- The `.trash` entry is not a normal editable folder. Users must not upload, drag, rename, copy, move, or delete it through ordinary file actions.
- Users who can access a workspace may restore files from that workspace's recycle-bin view. Hidden project access boundaries still apply.
- Permanent deletion and clearing the recycle bin remain destructive governance actions and should continue to follow uploader, workspace administrator, or system administrator permissions.
- If users need long-term retention for chat exports or downloaded files, they should export/download to local storage rather than relying on the personal workspace.
- Chat message export actions should offer two target choices: export to local storage or export to the personal workspace.
- File download actions should use the same target-choice logic: download to local storage or download to the personal workspace.
- Moving files into `常用文件` has source-specific semantics: files under `对话文件` are moved into `常用文件`; explicitly selected local files are added into `常用文件`; project files may only be copied into the user's `常用文件`, never moved out of the project.
- Files under `常用文件` are excluded from the 30-day cleanup strategy by default unless the user deletes them or a future explicit cleanup rule is introduced.
- Project files copied into `常用文件` become personal copies. Project_R should record the source project, source file, and copy time, but it must not automatically sync later project-file changes into the personal copy or delete the personal copy when the project original is deleted.
- When a user later uses a personal copy that originated from project files, the UI may indicate that it is a project-file copy and may not be the latest project version.
- AI must not read files by default. Files from local selection, the personal workspace, or project files become readable only after the user explicitly references, sends, analyzes, or queries them through an authorized action.
- File context menus should include a "引用文件" action. Referenced files appear in a preview strip above the input box, where users can inspect and remove references before sending.
- A file reference applies to the current message only by default. After the message is sent, the reference must not automatically continue into later messages.
- If persistent conversation-level references are needed later, they should use an explicit action such as "固定引用到当前会话"; this must not be the default behavior.
- Local files remain ordinary user files on the user's computer. Users may select files from any local path; they do not need to first copy them into `Documents/Project_R/私人空间`.
- A local selected file crosses into Project_R only when the user confirms sending, analysis, or saving. Project_R should show the source, target scope, sent content form, and retention behavior before the crossing.
- The personal workspace is not a company project, not a project file source, not a personal knowledge base, not a personal memory system, and not a GBrain source by default.
- Personal workspace files exist only to help the owning user reference temporary personal material during conversations.
- Company knowledge creation is an organization-level and administrator-governed process. Personal workspace files must not directly or indirectly become company knowledge candidates, enter the company knowledge base, or enter GBrain `company-wiki`.
- If personal material truly needs to become company knowledge, it must leave the personal workspace path and be collected, reviewed, and ingested through the administrator company-knowledge workflow.
- Ordinary chat in the personal workspace does not automatically query company knowledge. When the user explicitly uses `/query` or the knowledge query entry point, the personal workspace may query the company-wide `company-wiki`.
- The personal workspace has no project source by default. Only project workspaces may query their current project source.
- Personal workspace conversations and project conversations are independent. The personal workspace has no current project context.
- Personal workspace files must not use "save to current project files" semantics. They may only offer a "复制到项目" action.
- After choosing "复制到项目", Project_R shows the user a list of accessible or joined projects. The user manually selects the target project, and the file is copied by default into that project's `99-未归档文件`.
- Copying into a project must check the user's upload permission for the target project. Being able to enter or search a project does not automatically mean the user may copy files into that project.
- After the copy, the project copy follows the target project's permissions, audit logs, per-workspace `.trash` recycle-bin behavior, and GBrain project source rules.
- Project file "一键录入项目知识库" is available only to system administrators or administrators of that project. Ordinary project visitors and ordinary members cannot trigger one-click project knowledge ingest.

## Consequences

- Product language becomes clearer: local files are "本机选择文件", server-held personal files belong to `{username}的工作台`, and shared project files are "项目资料".
- Project_R avoids maintaining a second file-management system for a fixed local private folder.
- The UI must not label the personal workspace as project reference files or company project material.
- Existing code and documentation that mention `私人空间`, `本地私人工作区`, or `Project_R/私人空间` must be migrated or treated as legacy wording.
- Local Worker scope becomes simpler: read and preprocess explicitly selected local files, but do not scan or synchronize a fixed private workspace root.
- If a future personal knowledge base or personal memory feature is needed, it must be designed separately and must not be implied by the personal workspace.
