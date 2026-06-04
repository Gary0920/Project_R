# Project_R UI Design Reference for Stitch

## Goal

Use this document as the design baseline for optimizing the Project_R main workspace UI in Stitch. The objective is not to make a simplified chat app. The objective is to preserve the full Project_R working surface while improving visual clarity, spacing, hierarchy, and layout consistency.

Project_R is an internal AI office workstation for Chat, Agent execution, project files, customer intelligence, GBrain knowledge queries, prompts, skills, citations, review, and admin operations. Treat it as a professional desktop productivity tool, closer to an AI task execution IDE than a marketing website.

## Critical Instruction

Do not remove functional buttons, menus, tool panels, file operations, workspace operations, mode switches, admin/review actions, notification controls, or context controls.

If the current visual layout feels crowded, reorganize the controls into clearer groups, icon toolbars, segmented controls, overflow menus, drawers, or responsive compressed states. Do not solve visual density by deleting capabilities.

The previous redesign attempt lost many Project_R software buttons. That is unacceptable. Preserve the feature surface first, then improve the layout.

## Product Personality

Visual tone:

- Professional, calm, efficient, precise.
- Desktop productivity software, not a landing page.
- Proma-like shell: soft panels, thin borders, quiet background, rounded but not toy-like.
- High trust: user can see what the Agent is doing, what context it has, what files it touched, and what still needs review.
- Dense enough for repeated office use, but not visually noisy.

Avoid:

- Marketing hero layouts.
- Large decorative gradients or abstract blobs.
- Removing controls just to make the screen look minimal.
- Overly colorful or playful styling.
- Generic AI chat UI that only has a text box and messages.
- One-note purple/blue gradient themes.

## Current Visual Direction to Preserve

The current app uses:

- Light neutral shell with subtle gray background.
- Left sidebar as a rounded panel.
- Main chat/workbench as a rounded panel.
- Thin borders instead of heavy shadows.
- Soft green active state for ordinary selected items.
- Compact icon buttons for utility actions.
- 8-12 px radius for panels and controls.
- `Microsoft YaHei UI`, `Segoe UI`, and system sans fonts.
- Monospace only for code, paths, logs, command output.

Primary active-state tokens:

```css
--control-active-bg
--control-active-bg-hover
--control-active-border
--control-active-foreground
--control-active-shadow
```

Use soft green for normal active/selected states. Blue is allowed only for explicit selected capability hints or link/network semantics. Red is reserved for destructive or failed states. Yellow/orange is reserved for waiting, warning, and approval-needed states.

## Main Layout

Keep the app as a desktop workbench:

1. Left sidebar: workspace, mode, sessions, user controls.
2. Main center: Chat or Agent conversation and execution.
3. Optional right utility panel: project files, prompts, skills, source preview, review/context.
4. Optional split conversation mode: two chat panes side by side.
5. Optional overlays/drawers: search, settings, member management, confirmation, file preview, knowledge graph large canvas.

Do not replace this with a single centered chat column.

## Required Layout Regions

### Left Sidebar

Must preserve:

- App brand mark and app name.
- Agent / Chat segmented mode switch.
- Workspace selector area.
- Personal workspace group.
- Project workspace group.
- Customer workspace group.
- Workspace active state.
- Workspace create entry for admins.
- Workspace directory/search entry.
- Workspace member/admin shield button where allowed.
- Workspace rename action where allowed.
- Workspace delete action where allowed.
- Hidden/open project badge.
- New chat button.
- Search conversation button.
- Session list grouped by time.
- Session active state.
- Pinned session badge.
- Session overflow/more button.
- Sidebar user avatar, name, role.
- Notification button with unread count.
- Settings button.
- Logout button.
- Sidebar resize handle.

Allowed optimization:

- Improve spacing and grouping.
- Collapse low-frequency workspace row actions into an overflow menu.
- Use tooltips for icon-only buttons.
- Make active state clearer but still quiet.
- Improve scroll behavior and truncation.

Not allowed:

- Removing workspace groups.
- Hiding customer/project distinction.
- Removing member management entry.
- Removing notification/settings/logout.
- Removing session context actions.

### Top / Main Shell

Must preserve:

- Native desktop window control area where relevant.
- Tab bar.
- Add chat/tab button.
- Close tab button.
- Scratch pad entry.
- Error/notice/toast area.
- Notification toast.
- Undo deleted message toast.

Allowed optimization:

- Make the top area visually lighter.
- Compress tab labels when space is tight.
- Keep icons stable and familiar.

### Conversation Header

Must preserve:

- Current session title.
- Rename affordance.
- Current workspace/session context.
- Refresh/reload where present.
- Side-by-side conversation entry.
- Right-side utility panel entries:
  - Workspace files.
  - Prompt panel.
  - Skills panel.
  - Source/citation preview.
- Close/toggle behavior for panels.

Allowed optimization:

- Group header actions into a compact toolbar.
- Move low-frequency actions into a clearly labeled more menu.
- Preserve discoverability through tooltips.

### Chat / Agent Message Area

Must preserve:

- User and assistant messages.
- Markdown rendering.
- Code block rendering and copy.
- Message actions:
  - Copy.
  - Edit.
  - Delete context.
  - Regenerate.
  - Version/history activation where present.
  - Feedback/rating.
- Generated file card.
- Skill run card.
- Agent suggestion card.
- GBrain citation source pills/list.
- GBrain gaps/conflicts/warnings review submit entry.
- Jump bar / conversation minimap if enabled.
- Loading/thinking indicator.

Allowed optimization:

- Improve message width, rhythm, line height, and contrast.
- Make message action buttons visible on hover/focus.
- Place citation/source controls consistently at the bottom of answers.

Not allowed:

- Hiding citations.
- Removing feedback/review actions.
- Removing generated file and skill run cards.
- Collapsing Agent execution into plain text only.

### Composer / Input Area

Must preserve:

- Multi-line text input.
- Send button.
- Stop button while streaming/running.
- Attachment button.
- Paste/drop file handling.
- Attachment preview cards.
- Image thumbnail preview.
- PDF/file cards.
- Remove attachment action.
- Local file authorization state.
- Attachment source labels:
  - Local selected file.
  - Session upload.
  - Workspace reference.
- Model selector.
- Deep thinking / web / prompt / skills / query capability controls where present.
- Selected capability hint card for prompt, skill, or `/query`.
- Slash command suggestions.

Allowed optimization:

- Use an input tray with a top preview rail for attachments and references.
- Compress toolbar buttons to icon-only when width is tight.
- Use tooltips and aria labels for compressed buttons.
- Keep bottom toolbar height close to 32 px.

Not allowed:

- Removing file attachment previews.
- Treating local files as permanent personal workspace files.
- Removing model selection.
- Removing prompt/skill/query controls.
- Leaving `/query` text visible after selecting the knowledge-query capability if the UI already converts it to a capability card.

### Right Utility Panel

Must preserve panel modes:

- Workspace files.
- Prompt library.
- Skills list.
- Source/citation preview.

The right panel is not decoration. It is the current task/context/result surface.

Allowed optimization:

- Use tabs or segmented controls inside the panel if it improves clarity.
- Resize panel from roughly 300-880 px depending on content.
- Keep the panel anchored to the current session/workspace.

Not allowed:

- Replacing it with a static info card.
- Removing file operations.
- Removing source preview.

## Workspace File Panel Requirements

The file panel is a core Project_R surface. Preserve these operations:

- Breadcrumb/path bar.
- Back.
- Forward.
- Up one level.
- Upload.
- New folder.
- Refresh.
- More menu.
- Trash entry.
- File list.
- Folder list.
- File size.
- Knowledge ingest status.
- Preview.
- Open.
- Reference file into composer.
- Cut.
- Copy.
- Paste.
- Rename.
- Delete to trash.
- Restore from trash.
- Permanent delete.
- Clear trash.
- Drag move single item.
- External drag/upload.
- Project/customer knowledge ingest button.
- Pending ingest count.
- Knowledge graph entry.
- Timeline / graph / backlinks context where present.
- Entity merge candidate actions where present.
- File preview side pane.
- Preview resize handle.
- Large graph canvas overlay.

File list behavior:

- Default to compact list, not image grid.
- Do not show internal system directories such as `.git`, `derived`, `manifests`, `.pending_review`.
- `.trash` appears as recycle-bin entry but is protected from normal edit operations.
- Right-click menu follows Windows folder mental model.
- Disabled actions should remain visible but disabled when possible.

## Prompt Panel Requirements

Must preserve:

- Built-in Project_R prompt.
- Company prompt list.
- User prompt list.
- Prompt selected state.
- Prompt delete action for user prompts.
- Prompt source badge.
- Prompt search/filter if present.
- Add/edit user prompt where present.

Visual direction:

- Rows should be compact, scannable, and use soft green selected/hover state.
- Do not use a different active color system.

## Skills Panel Requirements

Must preserve:

- Skill row with icon.
- Skill display name.
- Skill description.
- Skill category/scope.
- Selecting a skill into the composer.
- Active/hover states.

Skills are user-invoked business capabilities. They must not be hidden behind an obscure generic menu.

## Source Preview Requirements

Must preserve:

- Source index.
- Source title/file/path.
- Markdown snippet preview.
- Clickable/openable source behavior where present.
- Citation relationship to the current AI answer.

This panel is key to trust and must remain readable.

## Settings / Admin Requirements

Settings and admin UI may be visually reorganized, but do not remove:

- Account/user settings.
- Model/provider settings.
- Prompt/templates settings.
- Archive management.
- Admin overview.
- User management.
- Knowledge reviews.
- GBrain status.
- GBrain service start/restart.
- GBrain sync/status/doctor.
- Query regression.
- Think regression.
- Quality reports/trends/export.
- GBrain maintenance.
- Jobs.
- Citation fixer.
- Citation fixer poll/rollback.
- Dream cycle / worker diagnostics where present.
- Contradiction probe configuration/runs.
- Audit logs.
- Client update dialog and forced update behavior.

Admin panels can be dense. Prefer tables, tabs, accordions, and status cards over large marketing-style cards.

## Agent Execution UI Direction

Agent mode must feel like an execution workstation, not just a chat clone.

Preferred structure:

- Goal.
- Agent understanding.
- Plan.
- Current step.
- Tool calls.
- File changes.
- Required approvals.
- Result.
- Verification/test summary.

Default display should show high-level summaries and current state. Full logs, command output, diffs, and raw tool data should be expandable.

Required Agent states:

- Draft.
- Planning.
- Running.
- Waiting Approval.
- Need Review.
- Failed.
- Completed.
- Archived.

Step/tool states:

- Waiting.
- Running.
- Completed.
- Needs confirmation.
- Failed.

## Business Rules That Affect UI

Project_R has strict data boundaries:

- Normal Chat does not automatically query GBrain.
- GBrain is only used through explicit `/query`, a knowledge entry, or selected knowledge Skill.
- Personal workspace is not a permanent personal file library.
- Long-term business files belong in project or customer workspace file panels.
- Session attachments are temporary conversation context.
- Project/customer files require permission-aware access.
- Customer intelligence is a restricted source and must not visually look like public company knowledge.

Reflect these boundaries in labels and layout. Do not imply that local attachments are automatically saved, indexed, or shared.

## Visual System

Use:

- Background: very light gray or app-neutral shell.
- Panels: white or near-white with thin neutral border.
- Active: soft green.
- Text: high-contrast neutral for primary, muted gray for secondary.
- Destructive: red only for destructive/failed.
- Warning: amber/yellow only for approval/waiting/risk.
- Success: green but distinct from normal active state.
- Radius: 8 px for controls, 10-12 px for shell panels.
- Border: thin, low-contrast.
- Shadow: subtle only for floating overlays, dialogs, and active elevation.

Do not:

- Use heavy neon gradients.
- Use large glassmorphism cards.
- Put cards inside cards unnecessarily.
- Use oversized headings in compact tool panels.
- Scale font by viewport width.
- Use negative letter spacing.

## Typography

Default:

- Chinese UI: `Microsoft YaHei UI`, `Segoe UI`, system sans.
- Body text: 13-15 px.
- Sidebar/session rows: 13-15 px.
- Headers in panels: 14-16 px.
- Compact metadata: 11-12 px.
- Code/log/path: `JetBrains Mono`, `Fira Code`, `Consolas`, monospace, 12-14 px.

Text must truncate gracefully in:

- Session titles.
- Workspace names.
- File names.
- Source paths.
- Model names.
- Skill names.
- Prompt descriptions.

## Responsive / Density Behavior

Minimum desktop target:

- 800 x 600 remains usable.
- Right panel may collapse or become overlay at narrow width.
- Composer toolbar labels may hide, leaving icons.
- Sidebars should preserve icon affordances and tooltips.
- Split mode should only activate when enough width exists.

Do not let text overlap controls. Do not allow attachment cards or long filenames to widen the composer or file panel unexpectedly.

## Desired Improvement Direction

Improve the current design by:

- Clarifying the three primary surfaces: navigation, work, context.
- Making toolbars more predictable.
- Reducing repeated visual weight between primary and secondary controls.
- Improving file panel density and path-bar clarity.
- Making Agent mode visibly different from Chat mode through execution-state structure.
- Making source/citation review more trustworthy and easier to scan.
- Keeping all existing capabilities discoverable.

## Files Included in This Reference Pack

Use these files as implementation and feature-surface reference:

- `frontend-ui-code/src/renderer/pages/AppPage.tsx`: main app workspace, chat, composer, panels, modals.
- `frontend-ui-code/src/renderer/components/WorkspaceSelector.tsx`: workspace groups and management entry.
- `frontend-ui-code/src/renderer/components/WorkspaceFilePanel.tsx`: project/customer file panel, preview, graph/timeline tools.
- `frontend-ui-code/src/renderer/components/PromptPanel.tsx`: prompt library.
- `frontend-ui-code/src/renderer/components/TabBar.tsx`: multi-tab top bar.
- `frontend-ui-code/src/renderer/components/SettingsModal.tsx`: settings/admin panels.
- `frontend-ui-code/src/renderer/components/LineIcons.tsx`: icon mapping.
- `frontend-ui-code/src/renderer/styles.css`: current visual tokens and component CSS.
- `project-docs/ui-design-language.md`: full Project_R UI design language.

## Stitch Output Requirements

When generating a redesign:

1. Preserve all major controls and feature groups listed above.
2. If a control is moved into an overflow menu, name the menu and list the moved controls.
3. Show Chat mode and Agent mode states.
4. Show right utility panel states: files, prompts, skills, source preview.
5. Show composer with attachments and selected capability.
6. Show at least one GBrain citation/source preview state.
7. Show file panel with breadcrumb, file rows, ingest status, preview, and context menu behavior.
8. Do not produce a landing page.
9. Do not remove admin/GBrain maintenance concepts if showing settings.
10. Prefer a complete desktop app mockup over isolated decorative components.

