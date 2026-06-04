# ADR 0020: Project_R UI Shells for GBrain-Native Capabilities

Date: 2026-06-04

## Status

Accepted

## Context

Project_R is adapting GBrain as the knowledge-system core. GBrain already provides mature primitives through schema packs, enrich skills, MCP operations, CLI commands, Admin Dashboard, graph/timeline/backlinks operations, source sync, query, think, citation, jobs, and maintenance.

Gary confirmed that Project_R must not modify or replace mature GBrain architecture. Project_R should be the business entry point, permission layer, preprocessing layer, backend persistence layer, query/operation forwarder, and UI surface.

At the same time, ordinary Project_R users need customer and project intelligence surfaces that are easier to use than raw GBrain CLI/MCP/Admin tools.

## Decision

Project_R may build business UI shells for GBrain-native capabilities, but must not duplicate the underlying GBrain knowledge logic.

The customer workspace may expose a `客户情报` entry with tabs such as:

- `画像概览`
- `图谱`
- `时间线`
- `实体处理`
- `GBrain 状态`

This UI is a Project_R business shell. Buttons, filters, graph views, timelines, enrichment actions, entity handling, and status cards must call GBrain-native capabilities through Project_R-controlled adapters and source-scoped authorization.

The Project_R shell owns:

- Project_R login identity and workspace permissions
- ordinary-user versus workspace-admin versus system-admin gating
- operation confirmations and cost/scope warnings
- audit logs and notifications
- user-friendly rendering of GBrain results
- source-file preview routing through Project_R file permissions

GBrain owns:

- schema packs and page type semantics
- entity detection and enrichment behavior
- graph, timeline, backlinks, citation, query, think, source sync, jobs, maintain, and contradiction logic
- GBrain Admin Dashboard and native CLI/MCP operation contracts

Ordinary customer workspace members may view customer profiles, graph, timeline, sources, and `/query` results. They may upload source files. They must not trigger GBrain writes such as Entity Enrichment, entity merge, alias/relationship edits, source cleanup, rollback, maintain, dream cycle, citation-fixer, or contradiction probe.

System administrators and customer workspace administrators may trigger controlled GBrain write operations from the Project_R shell after confirming scope, cost, and possible entity/relationship changes.

Project workspaces may later expose a `项目洞察` entry for project summaries, project timelines, risk/change/decision signals, related people/companies, source evidence, and retrospective entry points. This remains lower priority than customer intelligence.

The company-wide knowledge base will not get an ordinary-user `知识地图` UI in the current redesign. Ordinary users use `/query`; administrators use the existing GBrain status, regression, and maintenance surfaces.

## Consequences

- Project_R can give ordinary users a usable business interface without forking GBrain's knowledge system.
- The implementation must check for existing GBrain operations before adding Project_R code.
- Missing GBrain capability should be represented as pending integration or upstream capability work, not silently reimplemented in Project_R.
- Future GBrain Admin Dashboard pages for graph/enrichment should be linked or embedded when practical rather than rebuilt in Project_R.
