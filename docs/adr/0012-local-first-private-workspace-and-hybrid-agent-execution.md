# ADR 0012: Local-First Private Workspace and Hybrid Agent Execution

Date: 2026-05-31

## Status

Superseded by [ADR 0013: Personal Staging Area and Explicit Local File Selection](0013-personal-staging-area-and-explicit-local-file-selection.md)

## Context

Project_R is a company collaboration AI application, not only a personal desktop assistant. Company workflows need shared project files, source-scoped knowledge, model-key governance, permission checks, audit logs, notifications, and administrator-managed knowledge.

The previous domain model treated user private material as another Project_R-managed server-side source under `workspace_data/user/{username}`. That model is simple for backend implementation, but it creates long-term problems:

- Private files, temporary attachments, generated drafts, project ingestion, PDF/drawing extraction, media transcription, and chat calls can all accumulate on the backend.
- Backend concurrency becomes harder to scale if long-running Agent work is executed inside ordinary API request handling.
- Users lose a clear privacy boundary when personal files are automatically treated as server-hosted workspace material.
- A pure local-Agent model would avoid some server load, but it would weaken company permissions, shared project state, GBrain source scope, auditability, and business Skill governance.

Gary accepted the trade-off that the default private workspace should become local-first, even though this reduces automatic multi-device convenience. The private workspace is also scoped as a single-user, single-machine feature: each employee uses their own installed client on their own computer, and private files are not a collaboration surface.

## Decision

Project_R uses a hybrid Agent architecture:

- The default private workspace is local-first and single-user. Private files live on the user's computer by default. For standard installer/auto-update builds, the recommended default file root is the user's Documents folder under `Project_R/私人空间`; Electron `userData` stores manifest/config/authorization/index metadata, not the primary private files.
- Portable/no-install builds may optionally use a sibling data folder such as `Project_R-Data/私人空间`, but standard installer builds must not store private files inside the application installation directory.
- Project workspaces and the company knowledge base remain server-authoritative. Project and company files are stored under Project_R-managed backend paths and governed by Project_R permissions, audit logs, review flows, and GBrain source scope.
- The Project_R backend is the Agent control plane. It owns identity, permissions, workspace membership, GBrain source authorization, model profile routing, AgentRun / AgentJob state, audit logs, and notifications.
- Server Agent Workers execute shared or governed work: project ingestion, company knowledge ingestion, business Skills, project file generation, GBrain query/think/sync, and tasks requiring backend-held model keys.
- Local Agent Workers execute private or machine-local work: reading private files, local indexing, local preprocessing, local summaries, private drafts, and future desktop/Office automation.
- Private material may cross into backend, project, or company boundaries only after explicit user authorization. The UI must show what will be sent, the target scope, and whether it will be retained.
- Existing or transitional use of `workspace_data/user/{username}` is a compatibility or temporary server-upload path, not the long-term authority for the private workspace.

## MVP Boundary

The first Local Agent Worker release is a boundary and consent layer, not a fully autonomous desktop Agent.

In scope:

- Manage the app's local private workspace root and user-authorized local folders.
- Maintain a local file manifest with path, size, type, hash, last modified time, and user-facing source label.
- Read only files the user explicitly selects or files inside the configured private workspace root.
- Create image thumbnails/basic previews and extract text from Markdown, TXT, and readable PDFs.
- Produce local summaries or excerpts that the user can approve before backend submission.
- Submit only approved excerpts, summaries, or explicitly selected files to Project_R backend tasks.
- Copy selected local files into a project workspace only after explicit "save to project files" confirmation.

Out of scope for the first release:

- Scanning the whole disk or background-indexing arbitrary user folders.
- Automatic private-workspace upload, sync, backup, or multi-device replication.
- Local LLM hosting, local GBrain source sync, or offline answer generation.
- Arbitrary shell execution, unattended desktop automation, or direct writes to project/company backend paths.
- Bypassing Project_R backend permission checks or using company model keys directly from the client.

When the Local Agent Worker is unavailable, Project_R may fall back to temporary server-side attachment upload for web-only or compatibility flows, but the UI must label that as temporary upload processing rather than private workspace sync.

## Consequences

- The privacy boundary becomes clearer: local private material is not automatically uploaded, indexed into GBrain, or shared with projects.
- The private workspace does not need project-style member roles, shared permissions, or collaborative audit semantics; those remain project/company concerns.
- Backend load is reduced for private-file reading and preprocessing, while company/project tasks remain governable and auditable.
- Project_R keeps its company collaboration responsibilities instead of becoming a thin shell over independent local Agents.
- Multi-device sync for private workspace files is no longer automatic. It must be designed later as an explicit opt-in backup/sync feature, not as an implicit server-hosted default.
- Local Agent Worker trust, installation, update, health reporting, and capability grants become first-class engineering topics.
- Backend APIs must distinguish metadata, transient task uploads, project files, company knowledge files, and local-only private files.
- Long-running backend Agent work must use AgentJob/worker queues, worker pools, rate limits, status polling or push notifications, and resumable task state rather than blocking request threads.
- Tests and documentation should treat private, project, and company data boundaries as product invariants.
