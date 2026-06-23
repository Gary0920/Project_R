import { useEffect, useRef, useState, type MouseEvent } from "react";

import {
  WORKSPACE_PANEL_DEFAULT_WIDTH,
  WORKSPACE_PANEL_PREVIEW_WIDTH,
  SIDEBAR_COLLAPSED_WIDTH,
  auxiliaryPanelMaxWidth,
  clampAuxiliaryPanelWidth,
  clampSidebarWidth,
  clampWorkspacePanelWidth,
  readAuxiliaryPanelWidth,
  readSidebarCollapsed,
  readSidebarWidth,
  readWorkspacePanelWidth,
  workspacePanelMaxWidth,
  writeAuxiliaryPanelWidth,
  writeSidebarCollapsed,
  writeSidebarWidth,
  writeWorkspacePanelWidth,
} from "../panelWidths";

export function useAppShellPanels() {
  const [sidebarWidth, setSidebarWidth] = useState(readSidebarWidth);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarCollapsed);
  const [sidebarResizing, setSidebarResizing] = useState(false);
  const [workspacePanelWidth, setWorkspacePanelWidth] = useState(readWorkspacePanelWidth);
  const [workspacePanelResizing, setWorkspacePanelResizing] = useState(false);
  const [auxiliaryPanelWidth, setAuxiliaryPanelWidth] = useState(readAuxiliaryPanelWidth);
  const [auxiliaryPanelResizing, setAuxiliaryPanelResizing] = useState(false);
  const sidebarRef = useRef<HTMLElement | null>(null);
  const workspacePanelRef = useRef<HTMLElement | null>(null);
  const auxiliaryPanelRef = useRef<HTMLElement | null>(null);
  const workspacePanelWidthBeforePreviewRef = useRef<number | null>(null);

  function handleSidebarResizeStart(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    if (sidebarCollapsed) return;
    setSidebarResizing(true);
  }

  function toggleSidebarCollapsed() {
    setSidebarCollapsed((value) => !value);
  }

  function handleWorkspacePanelResizeStart(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    setWorkspacePanelResizing(true);
  }

  function handleAuxiliaryPanelResizeStart(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    setAuxiliaryPanelResizing(true);
  }

  function handleWorkspaceFilePreviewOpen() {
    if (workspacePanelWidthBeforePreviewRef.current === null) {
      workspacePanelWidthBeforePreviewRef.current = workspacePanelWidth;
    }
    const previewPanelWidth = clampWorkspacePanelWidth(WORKSPACE_PANEL_PREVIEW_WIDTH);
    setWorkspacePanelWidth((width) => Math.max(width, previewPanelWidth));
  }

  function handleWorkspaceFilePreviewClose() {
    const savedWidth = workspacePanelWidthBeforePreviewRef.current;
    workspacePanelWidthBeforePreviewRef.current = null;
    if (savedWidth !== null) {
      setWorkspacePanelWidth(clampWorkspacePanelWidth(savedWidth));
    } else {
      setWorkspacePanelWidth(clampWorkspacePanelWidth(WORKSPACE_PANEL_DEFAULT_WIDTH));
    }
  }

  useEffect(() => {
    writeSidebarWidth(sidebarWidth);
  }, [sidebarWidth]);

  useEffect(() => {
    writeSidebarCollapsed(sidebarCollapsed);
    if (sidebarCollapsed) {
      setSidebarResizing(false);
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    writeWorkspacePanelWidth(workspacePanelWidth);
  }, [workspacePanelWidth]);

  useEffect(() => {
    writeAuxiliaryPanelWidth(auxiliaryPanelWidth);
  }, [auxiliaryPanelWidth]);

  useEffect(() => {
    function handleWindowResize() {
      setSidebarWidth((width) => clampSidebarWidth(width));
      setWorkspacePanelWidth((width) => clampWorkspacePanelWidth(width));
      setAuxiliaryPanelWidth((width) => clampAuxiliaryPanelWidth(width));
    }
    window.addEventListener("resize", handleWindowResize);
    return () => window.removeEventListener("resize", handleWindowResize);
  }, []);

  useEffect(() => {
    if (!sidebarResizing) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const left = sidebarRef.current?.getBoundingClientRect().left ?? 0;
      setSidebarWidth(clampSidebarWidth(event.clientX - left));
    }

    function handleMouseUp() {
      setSidebarResizing(false);
    }

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [sidebarResizing]);

  useEffect(() => {
    if (!workspacePanelResizing) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const right = workspacePanelRef.current?.getBoundingClientRect().right ?? window.innerWidth;
      setWorkspacePanelWidth(clampWorkspacePanelWidth(right - event.clientX));
    }

    function handleMouseUp() {
      setWorkspacePanelResizing(false);
    }

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [workspacePanelResizing]);

  useEffect(() => {
    if (!auxiliaryPanelResizing) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const right = auxiliaryPanelRef.current?.getBoundingClientRect().right ?? window.innerWidth;
      setAuxiliaryPanelWidth(clampAuxiliaryPanelWidth(right - event.clientX));
    }

    function handleMouseUp() {
      setAuxiliaryPanelResizing(false);
    }

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [auxiliaryPanelResizing]);

  return {
    auxiliaryPanelMaxWidth,
    auxiliaryPanelRef,
    auxiliaryPanelResizing,
    auxiliaryPanelWidth,
    handleAuxiliaryPanelResizeStart,
    handleSidebarResizeStart,
    handleWorkspaceFilePreviewClose,
    handleWorkspaceFilePreviewOpen,
    handleWorkspacePanelResizeStart,
    setSidebarCollapsed,
    sidebarRef,
    sidebarCollapsed,
    sidebarDisplayWidth: sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : sidebarWidth,
    sidebarResizing,
    sidebarWidth,
    toggleSidebarCollapsed,
    workspacePanelMaxWidth,
    workspacePanelRef,
    workspacePanelResizing,
    workspacePanelWidth,
  };
}
