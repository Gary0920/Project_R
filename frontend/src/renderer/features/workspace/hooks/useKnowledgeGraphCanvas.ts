import { useEffect, useRef, useState, type MouseEvent, type WheelEvent } from "react";

import { clampGraphCanvasScale } from "../knowledgeGraphUtils";

export function useKnowledgeGraphCanvas() {
  const [knowledgeGraphCanvasView, setKnowledgeGraphCanvasView] = useState({ x: 0, y: 0, scale: 1 });
  const [knowledgeGraphCanvasPanning, setKnowledgeGraphCanvasPanning] = useState(false);
  const graphCanvasPanRef = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);

  useEffect(() => {
    if (!knowledgeGraphCanvasPanning) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "grabbing";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const drag = graphCanvasPanRef.current;
      if (!drag) return;
      setKnowledgeGraphCanvasView((view) => ({
        ...view,
        x: drag.originX + (event.clientX - drag.startX) / Math.max(0.7, view.scale),
        y: drag.originY + (event.clientY - drag.startY) / Math.max(0.7, view.scale),
      }));
    }

    function handleMouseUp() {
      graphCanvasPanRef.current = null;
      setKnowledgeGraphCanvasPanning(false);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [knowledgeGraphCanvasPanning]);

  function resetKnowledgeGraphCanvasView() {
    setKnowledgeGraphCanvasView({ x: 0, y: 0, scale: 1 });
  }

  function zoomKnowledgeGraphCanvas(delta: number) {
    setKnowledgeGraphCanvasView((view) => ({
      ...view,
      scale: clampGraphCanvasScale(view.scale + delta),
    }));
  }

  function handleKnowledgeGraphCanvasWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.12 : 0.12;
    zoomKnowledgeGraphCanvas(delta);
  }

  function handleKnowledgeGraphCanvasPanStart(event: MouseEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    const target = event.target;
    if (target instanceof Element && target.closest(".workspace-knowledge-map-node, button")) return;
    event.preventDefault();
    graphCanvasPanRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: knowledgeGraphCanvasView.x,
      originY: knowledgeGraphCanvasView.y,
    };
    setKnowledgeGraphCanvasPanning(true);
  }

  return {
    knowledgeGraphCanvasView,
    knowledgeGraphCanvasPanning,
    resetKnowledgeGraphCanvasView,
    zoomKnowledgeGraphCanvas,
    handleKnowledgeGraphCanvasWheel,
    handleKnowledgeGraphCanvasPanStart,
  };
}
