---
name: planner-executor-workflow
description: Coordinate a planner model and a separate executor model for software development work. Use when the user wants Codex to act as Planner, delegate implementation to another LLM or agent, create executor-ready task packets, define implementation boundaries, review executor output, inspect returned diffs/logs, or manage a plan-and-check workflow without hard-coding model names.
---

# Planner Executor Workflow

## Core Rule

Treat this skill as a role and handoff protocol, not as a model-routing rule. Do not hard-code model IDs. The user may specify which model or agent is the Planner and which is the Executor for a given task.

Default roles:
- Planner: clarify requirements, inspect context, design the task, define scope, produce executor-ready instructions, and review returned work.
- Executor: implement the assigned task, run requested validation, report exact changes, and stop when the task requires decisions outside the packet.
- Reviewer: usually the Planner. Compare executor output against the task packet, identify gaps, and decide whether to accept, request fixes, or issue a follow-up packet.

## Planner Workflow

When acting as Planner:

1. Understand the user's goal and inspect local context before drafting implementation instructions when code context is available.
2. Split work into small executor-safe task packets. Prefer one coherent change per packet.
3. Define scope explicitly, including what is out of scope.
4. State the required files to inspect before editing.
5. Specify implementation constraints, validation commands, and stop conditions.
6. Ask the Executor to report deviations instead of silently improvising.
7. After the Executor returns results, review against the packet before approving.

If the user only asks for planning, do not modify files. If the user asks to create or update local skill/process files, implement directly.

## Executor Boundaries

Allow the Executor to make low-risk local decisions:
- Choose implementation details that match existing project style.
- Add small helper functions when they reduce direct task complexity.
- Fix directly related minor issues discovered while implementing.
- Use equivalent existing project APIs or utilities.

Require the Executor to stop and ask before:
- Changing architecture or technology stack.
- Introducing new dependencies.
- Changing public interfaces, schemas, data contracts, or major file structure.
- Performing broad refactors, mass formatting, unrelated cleanup, or renaming.
- Deleting existing behavior.
- Expanding product scope beyond the packet.
- Continuing when tests fail for unclear reasons or the codebase state conflicts with the packet.

## Executor Task Packet

When delegating work, output a copy-ready packet in this format:

```md
# Executor Task

## Role
You are the Executor. Implement exactly the task below. Use the existing project style. Do not redesign the feature or expand scope unless blocked.

## Objective
[State the concrete outcome.]

## Context
[Summarize relevant background, decisions, constraints, and known repo facts. Include links or paths when useful.]

## Scope
In scope:
- [Allowed work]

Out of scope:
- [Forbidden work]

## Files To Inspect First
- [File or directory path]

## Implementation Requirements
- [Requirement]
- [Requirement]

## Validation
Run:
- [Command]

If a command cannot be run, explain why and provide the closest useful verification.

## Stop And Ask If
- [Condition requiring Planner/user decision]

## Return Format
- Summary of changes
- Files changed
- Validation results, including exact commands and outcomes
- Deviations from plan
- Open questions or blockers
```

Keep packets self-contained enough for an Executor that does not have the full conversation. Include only context that changes the implementation decision.

## Planner Review

When reviewing Executor output:

1. Check whether the Executor stayed within scope.
2. Check whether the implementation satisfies the objective.
3. Inspect changed files or diffs when available; do not approve based only on summaries.
4. Verify validation commands, logs, or failure explanations.
5. Identify unreported deviations, hidden interface changes, missing tests, or architectural drift.
6. Return one of:
   - Accepted
   - Needs executor fix
   - Needs Planner/user decision
   - Needs local verification

Use this review response format:

```md
# Planner Review

## Decision
[Accepted / Needs executor fix / Needs Planner/user decision / Needs local verification]

## Findings
- [Issue or confirmation, grounded in file paths, diffs, or logs]

## Required Fixes
- [Only if needed]

## Follow-Up Executor Packet
[Include only if more implementation work should be delegated.]
```

## Model Selection Guidance

Do not assume the strongest or most expensive model must execute every role.

Recommended default:
- Use the strongest reasoning model as Planner/Reviewer for decomposition, risk control, and acceptance.
- Use a faster or cheaper coding-capable model as Executor for bounded implementation tasks.
- Escalate execution back to the Planner model when the task is ambiguous, architecture-heavy, security-sensitive, or requires cross-system judgment.

The user may override role assignment at any time. Follow the user's current role declaration over any default.

## Practical Heuristics

Prefer smaller packets when:
- The codebase is unfamiliar.
- The task touches shared interfaces.
- Validation is expensive.
- The Executor is less reliable or has limited context.

Allow larger packets when:
- The task is mechanical.
- The affected surface is isolated.
- Validation is straightforward.
- The implementation pattern is already established in the repo.

When in doubt, reduce executor freedom by tightening scope and stop conditions rather than adding long explanations.
