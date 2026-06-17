import type { ChatContextTraceResponse, ChatSourceResponse } from "../../shared/api/types";
import { normalizeSourceEvidence } from "./sourceEvidence";

export type KnowledgeSourcePreview = {
  contextTrace?: ChatContextTraceResponse | null;
  index: number;
  source: ChatSourceResponse;
  sessionId?: number | null;
};

export type NormalizedKnowledgeSource = {
  content: string;
  file: string;
  locator: string;
  scopeLabel: string;
  title: string;
};

export function normalizeKnowledgeSource(source: ChatSourceResponse): NormalizedKnowledgeSource {
  const evidence = normalizeSourceEvidence(source, 1);
  return {
    content: evidence.excerpt,
    file: evidence.fileName,
    locator: evidence.locatorLabel,
    scopeLabel: evidence.scopeLabel,
    title: evidence.title,
  };
}

export function sourceScopeLabel(source: ChatSourceResponse) {
  const file = `${source.file || ""} ${source.source_file || ""}`.toLowerCase();
  if (file.includes("customer") || file.includes("crm")) return "客户情报";
  if (file.includes("company-wiki") || file.includes("company")) return "公司知识";
  if (file.includes("project")) return "项目资料";
  if (source.source_file?.startsWith("http")) return "外部来源";
  return "授权来源";
}

export function sourceLocatorLabel(source: ChatSourceResponse) {
  const parts = [
    source.section_path,
    source.source_page != null ? `第 ${source.source_page} 页` : null,
    source.source_line != null ? `第 ${source.source_line} 行` : null,
    source.source_locator,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "片段定位由 GBrain 引用返回";
}
