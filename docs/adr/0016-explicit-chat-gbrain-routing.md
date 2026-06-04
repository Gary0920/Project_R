# ADR 0016: Explicit Chat and GBrain Routing

Date: 2026-06-04

## Status

Accepted

## Context

Project_R now has both ordinary Chat behavior and a GBrain-backed knowledge query path. Earlier product discussions repeatedly risked blurring these two capabilities: ordinary Chat could be treated as a smart business assistant, while GBrain could be treated as an always-on background retrieval layer.

Gary confirmed on 2026-06-04 that different Chat sessions and GBrain should remain independent. Project_R already has built-in prompt configuration through `backend/prompt_presets/global-base-prompt.md`, user-defined prompts, and session-level prompts, so ordinary Chat can have business discipline without silently querying knowledge sources.

## Decision

Ordinary Chat and GBrain are separate routes.

- Ordinary Chat does not automatically query GBrain.
- Ordinary Chat behavior is governed by Project_R built-in prompts, the global base prompt, user-defined prompts, session prompts, current user input, current attachments, and explicit file references.
- Trusted company, project, or customer knowledge answers must use explicit `/query`, the knowledge query entry point, or an explicitly selected knowledge Skill.
- Every GBrain call must pass through Project_R backend permission checks and source-scope selection before calling the GBrain adapter.
- Personal workspace `/query` only queries the company-wide `company-wiki` source.
- Project workspace `/query` queries `company-wiki + the current project source`: global rules and shared process knowledge come from `company-wiki`, while project-specific files, meetings, emails, drawings, and events come from the current project source.
- Customer workspace `/query` only queries restricted customer intelligence data refined and absorbed by GBrain from `workspace_data/customer/`; it does not combine `company-wiki` or project sources. `customer-reference`, where still present, is an early implementation source id, not the product term.
- Ordinary Chat may suggest using `/query` when the user asks for facts that should come from company, project, or customer knowledge, but it must not fabricate retrieved knowledge or citations.
- Agent mode and business Skills may call GBrain only when the user has explicitly started, selected, or authorized that workflow.

## Consequences

- Chat remains fast and lightweight for drafting, explanation, rewriting, brainstorming, and general assistance.
- GBrain remains the auditable route for citation-bearing knowledge answers.
- Product behavior is easier to reason about: prompt discipline and knowledge retrieval are not the same mechanism.
- Future automatic intent routing or automatic knowledge retrieval must be treated as a new product decision, not as an implicit implementation detail.
