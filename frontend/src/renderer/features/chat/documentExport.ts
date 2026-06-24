import type { ApiClientOptions } from "../../shared/api/client";
import { ApiError } from "../../shared/api/client";

export type DocumentExportFormat = "pdf" | "docx";

function parseFilename(contentDisposition: string | null, fallback: string) {
  if (!contentDisposition) return fallback;
  const utfMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch?.[1]) {
    try {
      return decodeURIComponent(utfMatch[1]);
    } catch {
      return utfMatch[1];
    }
  }
  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] || fallback;
}

export async function exportDocumentContent(
  options: ApiClientOptions,
  payload: { content: string; title?: string; format: DocumentExportFormat },
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${options.baseUrl}/documents/export`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    if (response.status === 401) {
      options.onUnauthorized?.();
    }
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail || detail;
    } catch {
      // Keep status text when body is not JSON.
    }
    throw new ApiError(detail, response.status);
  }

  const fallback = payload.format === "pdf" ? "project-r-document.pdf" : "project-r-document.docx";
  const filename = parseFilename(response.headers.get("content-disposition"), fallback);
  const blob = await response.blob();
  return { blob, filename };
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function inferDocumentTitle(content: string) {
  const firstLine = content
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean);
  if (!firstLine) return "Project_R 文档";
  return firstLine.replace(/^#+\s*/, "").replace(/^Subject:\s*/i, "").slice(0, 120) || "Project_R 文档";
}
