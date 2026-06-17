import type { ChatSourceResponse } from "../../shared/api/types";

export type SourceEvidenceKind = "all" | "company" | "project" | "customer" | "external" | "unknown";
export type SourceEvidenceFilter = SourceEvidenceKind | "issues";
export type SourceEvidenceStatusLevel = "normal" | "limited" | "warning" | "conflict" | "gap";

export type SourceEvidenceIssue = {
  kind: "gap" | "conflict" | "warning";
  text: string;
};

export type SourceEvidence = {
  displayTitle: string;
  evidenceExcerpt: string;
  excerpt: string;
  fileName: string;
  id: string;
  index: number;
  isCitedInThisAnswer: boolean;
  issues: SourceEvidenceIssue[];
  kind: Exclude<SourceEvidenceKind, "all">;
  limitations: string[];
  locatorLabel: string;
  metadataOnly: boolean;
  originalSourceFile: string;
  page?: number | null;
  pageSlug?: string | null;
  line?: number | null;
  rawSource: ChatSourceResponse;
  rowNum?: number | string | null;
  scopeLabel: string;
  sourceSlug?: string | null;
  statusLevel: SourceEvidenceStatusLevel;
  statusText: string;
  title: string;
};

export type SourceEvidenceContext = {
  conflicts?: string[];
  gaps?: string[];
  warnings?: string[];
};
