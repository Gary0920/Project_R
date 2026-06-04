# ADR 0017: Business Files Belong in Project or Customer Workspaces

Date: 2026-06-04

## Status

Accepted, amended by [ADR 0015: Retire Personal File Panel](0015-retire-personal-file-panel.md) and [ADR 0019: GBrain-Ready Preprocessing Source Repos](0019-gbrain-ready-preprocessing-source-repos.md)

## Context

After retiring the personal file panel, Project_R still needs a clear rule for files that should be retained, shared, audited, ingested into GBrain, used in project retrospectives, or referenced by business answers.

Gary confirmed on 2026-06-04 that the personal workspace should remain a personal conversation and prompt-context entry only. It should not become a fallback file system for downloads, exports, generated documents, project references, or personal knowledge ingestion.

## Decision

Project_R business files belong in project or customer workspaces.

- Project/customer workspaces are the only product containers for business files that need long-term retention, sharing, permissions, audit logs, recycle-bin governance, GBrain source status, ingestion, review, retrospective workflows, or citation by project/customer knowledge answers.
- The personal workspace keeps conversations, prompt context, session attachments, explicit references, and local export/download actions, but it does not provide a personal file panel or a governed business file store.
- Session attachments and local file selections are temporary or per-action context. The personal workspace must not provide cross-workspace save actions into project/customer materials. Project-related work should happen inside the relevant project workspace; customer-related work should happen inside the relevant customer workspace.
- Business files enter project/customer governance through upload, generation, or confirmed save actions inside the current project/customer workspace. They do not cross from the personal workspace into another workspace through a target picker.
- Export and download flows target the local filesystem by default; Project_R does not offer "export to personal workspace" or "download to personal workspace".

## Consequences

- File governance is simpler: shared business files have one home and one permission/audit model.
- Personal workspace cleanup can focus on conversation/session attachment retention instead of becoming a second document-management system.
- Future UI or backend work must not reintroduce personal file-panel flows without a new ADR.
