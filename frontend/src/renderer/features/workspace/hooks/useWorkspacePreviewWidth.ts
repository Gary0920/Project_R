import { useEffect, useState, type MouseEvent, type RefObject } from "react";

import {
  clampPreviewWidth,
  PREVIEW_DEFAULT_WIDTH,
  readPreviewWidth,
  writePreviewWidth,
} from "../workspaceFilePanelUtils";

export function useWorkspacePreviewWidth({
  hasSidecar,
  layoutRef,
  resetKey,
}: {
  hasSidecar: boolean;
  layoutRef: RefObject<HTMLDivElement | null>;
  resetKey?: string | null;
}) {
  const [previewWidth, setPreviewWidth] = useState(readPreviewWidth);
  const [previewResizing, setPreviewResizing] = useState(false);

  useEffect(() => {
    if (!hasSidecar) return;
    const layout = layoutRef.current;
    if (!layout || typeof ResizeObserver === "undefined") return;
    const updatePreviewWidth = () => {
      setPreviewWidth((width) => clampPreviewWidth(width, layout.getBoundingClientRect().width));
    };
    updatePreviewWidth();
    const observer = new ResizeObserver(updatePreviewWidth);
    observer.observe(layout);
    return () => observer.disconnect();
  }, [hasSidecar, layoutRef]);

  useEffect(() => {
    if (!hasSidecar) return;
    setPreviewWidth((width) => clampPreviewWidth(Math.max(width, PREVIEW_DEFAULT_WIDTH), layoutRef.current?.getBoundingClientRect().width));
  }, [hasSidecar, layoutRef, resetKey]);

  useEffect(() => {
    writePreviewWidth(previewWidth);
  }, [previewWidth]);

  useEffect(() => {
    if (!previewResizing) return;

    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const layout = layoutRef.current;
      if (!layout) return;
      const rect = layout.getBoundingClientRect();
      setPreviewWidth(clampPreviewWidth(rect.right - event.clientX, rect.width));
    }

    function handleMouseUp() {
      setPreviewResizing(false);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [layoutRef, previewResizing]);

  function handlePreviewResizeStart(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    setPreviewResizing(true);
  }

  return {
    previewWidth,
    previewResizing,
    handlePreviewResizeStart,
  };
}
