import { useEffect, useRef, useState } from "react";

import { fetchWorkspaceFileBlob } from "../api";
import { getFileKind, type WorkspaceFilePreview } from "../workspaceFilePanelUtils";
import type { ApiClientOptions } from "../../../shared/api/client";
import type { WorkspaceFileItemResponse } from "../../../shared/api/types";

export function useWorkspaceFilePreview({
  apiOptions,
  workspaceId,
  onBeforeOpen,
  onPreviewOpen,
  onPreviewClose,
}: {
  apiOptions: ApiClientOptions;
  workspaceId: number | null;
  onBeforeOpen?: () => void;
  onPreviewOpen?: () => void;
  onPreviewClose?: () => void;
}) {
  const [filePreview, setFilePreview] = useState<WorkspaceFilePreview | null>(null);
  const previewObjectUrlRef = useRef<string | null>(null);

  function revokePreviewObjectUrl() {
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
  }

  function closeFilePreview() {
    revokePreviewObjectUrl();
    setFilePreview(null);
    onPreviewClose?.();
  }

  async function openFilePreview(item: WorkspaceFileItemResponse) {
    if (!workspaceId || item.type === "directory") return;
    onPreviewOpen?.();
    onBeforeOpen?.();
    revokePreviewObjectUrl();
    const kind = getFileKind(item.name);
    setFilePreview({ item, kind, status: "loading" });
    try {
      const blob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
      if (kind === "image" || kind === "pdf") {
        const objectUrl = URL.createObjectURL(blob);
        previewObjectUrlRef.current = objectUrl;
        setFilePreview({ item, kind, status: "ready", objectUrl });
        return;
      }
      if (kind === "code" || item.name.toLowerCase().endsWith(".txt") || item.name.toLowerCase().endsWith(".md")) {
        const text = await blob.text();
        setFilePreview({ item, kind, status: "ready", text: text.slice(0, 60_000) });
        return;
      }
      const objectUrl = URL.createObjectURL(blob);
      previewObjectUrlRef.current = objectUrl;
      setFilePreview({ item, kind, status: "ready", objectUrl });
    } catch (previewError: unknown) {
      setFilePreview({
        item,
        kind,
        status: "failed",
        error: previewError instanceof Error ? previewError.message : "文件预览失败",
      });
    }
  }

  useEffect(() => {
    return () => revokePreviewObjectUrl();
  }, []);

  return {
    filePreview,
    closeFilePreview,
    openFilePreview,
  };
}
