import type { GeneratedFileResponse } from "../../shared/api/types";

export async function downloadGeneratedFile(baseUrl: string, token: string | null, file: GeneratedFileResponse) {
  const response = await fetch(`${baseUrl}${file.download_url}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error("文件下载失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
