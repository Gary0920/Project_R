# ADR 0013: Open Projects, Hidden Workspaces, and Work Groups

## Status

Accepted

## Context

Project_R previously treated project workspace access as invite-only for ordinary users. That model was safe, but too heavy for normal company project work because most project workspaces are not sensitive and should be discoverable by staff.

Gary confirmed a new product rule: project workspaces should be open to all users by default, while sensitive or non-public workspaces should be explicitly hidden. Hidden projects should only be searchable and accessible to users or work groups added in project member management.

## Decision

- Company project workspaces are open by default.
- Open projects are searchable and accessible to all active users.
- Hidden projects are only searchable and accessible to system administrators, explicit workspace members, and users whose `work_group` is in the workspace group allowlist.
- `WorkspaceMember` remains the place for explicit person-level access and scoped workspace admin role.
- `WorkspaceGroupAccess` records group-level hidden project access.
- User management exposes `work_group` as the operational team/group field; it replaces created-time as the relevant admin-facing user attribute.

## Consequences

- Membership no longer means “everyone who can enter this project.” In open projects, many users can access the project without a `WorkspaceMember` row.
- Hidden project access must always check both explicit members and group allowlist.
- Project admins can use one panel to manage explicit users, group allowlist, and hidden/open visibility.
- Future multi-group membership would require a new user-group model; the current MVP deliberately keeps one `work_group` per user.
