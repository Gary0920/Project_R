import type { KnowledgeStatusResponse } from "../../../shared/api/types";

export type KnowledgeMetric = {
  label: string;
  value: string | number;
};

export function knowledgeStatusMetrics(
  status: KnowledgeStatusResponse | null,
  statusLabel: (value?: string | null) => string,
  yesNo: (value?: boolean | null) => string,
): KnowledgeMetric[] {
  return [
    { label: "HTTP 服务", value: statusLabel(status?.service?.status) },
    { label: "source 注册", value: statusLabel(status?.source?.status) },
    { label: "语义检索", value: yesNo(status?.semantic_search_ready) },
    { label: "页面", value: status?.page_count ?? status?.indexed_files ?? "-" },
    { label: "片段", value: status?.chunk_count ?? status?.indexed_chunks ?? "-" },
    { label: "嵌入模型", value: status?.embedding?.model ?? status?.embedding_model ?? "-" },
    { label: "最近编译", value: status?.ingest?.summary?.compiled ?? "-" },
    { label: "doctor 分数", value: status?.doctor?.health_score ?? "-" },
  ];
}
