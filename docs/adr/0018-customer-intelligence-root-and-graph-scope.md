# ADR 0018: Customer Intelligence Root and Graph Scope

Date: 2026-06-04

## Status

Accepted, amended by [ADR 0020: Project_R UI Shells for GBrain-Native Capabilities](0020-project-r-gbrain-native-ui-shells.md)

## Context

Project_R has a `workspace_data/customer/` path and customer workspaces. Earlier documentation often described the current implementation as `customer-reference`, which made the product boundary look like a generic reference source or another project-like workspace.

Gary clarified on 2026-06-04 that `workspace_data/customer/` has a different meaning from `workspace_data/project/`. It is a CRM/customer-intelligence material root for sales scenarios.

## Decision

`workspace_data/customer/` is the customer intelligence root.

- It stores customer emails, meeting records, contacts, companies, customer-project relationships, communication events, and sales judgment signals.
- It is not another project directory and should not simply copy the project workspace model.
- Its purpose is to feed customer intelligence material into GBrain, then use GBrain Entity Enrichment to build People Graph, Company Graph, and Project Graph.
- The product goal is to help sales teams evaluate decisions around a customer, a company, a project, or a person involved in those relationships.
- Customer workspace `/query` only queries the customer intelligence data that GBrain has refined, absorbed, and organized from customer materials.
- Customer workspace `/query` does not combine `company-wiki` and does not query project sources.
- `customer-reference`, where still present in code, manifests, scripts, or tests, is an early MVP validation source id. It is not the product-level term and is not the formal quality baseline.
- Existing `customer-reference` generated artifacts, source registration, and source-scoped clients may be cleaned up after explicit preflight. Original Markdown source files and customer workspace structure should be preserved for rerunning through the corrected customer intelligence flow.
- Project_R does not design or replace GBrain's customer-intelligence schema. Project_R preprocesses customer materials into GBrain-friendly source Markdown and forwards GBrain-native enrichment, graph, timeline, backlinks, query, and think operations.

## Consequences

- Product language should use "客户情报", "客户画像", "客户情报源", or "Customer Intelligence Source" instead of treating `customer-reference` as the product concept.
- Customer work must prioritize entity extraction, relationship enrichment, graph quality, citation quality, and CRM decision workflows.
- Future implementation should use GBrain-native schema, enrich, entity detection, graph, timeline, and backlinks wherever possible. Project_R may expose a `客户情报` UI shell, but it must remain an adapter and visualization layer over GBrain-native capabilities.
