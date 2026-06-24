import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useState } from "react";
import { useTabNavigation } from "./useTabNavigation";
import type { SourcePreview } from "../messageContent";
import type { Tab } from "../tabs-state";
import type { ChatSourceResponse } from "../../../shared/api/types";

const source: ChatSourceResponse = {
  file: "gbrain:company-wiki/example",
  source_title: "Example",
  section_path: "Example",
  content: "source content",
  score: 0.9,
};

function useNavigationHarness(initial?: {
  activeSessionId?: number | null;
  activeTabId?: string;
  activeWorkspaceId?: number | null;
  sourcePreview?: SourcePreview | null;
  utilityPanel?: string | null;
  tabs?: Tab[];
}) {
  const [tabs, setTabs] = useState<Tab[]>(
    initial?.tabs ?? [
      { id: "chat-1", sessionId: 1, workspaceId: 10, title: "One" },
      { id: "chat-2", sessionId: 2, workspaceId: 20, title: "Two" },
    ],
  );
  const [activeTabId, setActiveTabId] = useState(initial?.activeTabId ?? "chat-1");
  const [activeSessionId, setActiveSessionId] = useState<number | null>(initial?.activeSessionId ?? 1);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<number | null>(initial?.activeWorkspaceId ?? 10);
  const [splitPaneSessionIds, setSplitPaneSessionIds] = useState<Record<"left" | "right", number | null>>({
    left: null,
    right: null,
  });
  const [utilityPanel, setUtilityPanel] = useState<string | null>(initial?.utilityPanel ?? null);
  const [sourcePreview, setSourcePreview] = useState<SourcePreview | null>(initial?.sourcePreview ?? null);
  const [showScratchPad, setShowScratchPad] = useState(true);
  const [mode, setMode] = useState<"chat" | "agent">("chat");

  const actions = useTabNavigation({
    tabs,
    setTabs,
    activeTabId,
    setActiveTabId,
    activeSessionId,
    setActiveSessionId,
    activeWorkspaceId,
    setActiveWorkspaceId,
    sideBySideOpen: true,
    activeSplitPane: "left",
    setSplitPaneSessionIds,
    utilityPanel,
    setUtilityPanel,
    sourcePreview,
    setSourcePreview,
    setShowScratchPad,
    setMode,
  });

  return {
    actions,
    state: {
      activeSessionId,
      activeTabId,
      activeWorkspaceId,
      mode,
      showScratchPad,
      sourcePreview,
      splitPaneSessionIds,
      tabs,
      utilityPanel,
    },
  };
}

describe("useTabNavigation", () => {
  it("selects a tab, switches workspace, and updates the active split pane", () => {
    const { result } = renderHook(() => useNavigationHarness());

    act(() => result.current.actions.handleSelectTab("chat-2"));

    expect(result.current.state.activeTabId).toBe("chat-2");
    expect(result.current.state.activeSessionId).toBe(2);
    expect(result.current.state.activeWorkspaceId).toBe(20);
    expect(result.current.state.splitPaneSessionIds.left).toBe(2);
    expect(result.current.state.showScratchPad).toBe(false);
  });

  it("clears active session when the active tab belongs to another workspace", () => {
    const { result } = renderHook(() => useNavigationHarness());

    act(() => result.current.actions.handleWorkspaceChanged(99));

    expect(result.current.state.activeWorkspaceId).toBe(99);
    expect(result.current.state.activeTabId).toBe("");
    expect(result.current.state.activeSessionId).toBeNull();
  });

  it("clears source preview when active session no longer matches the preview", () => {
    const { result } = renderHook(() =>
      useNavigationHarness({
        activeSessionId: 1,
        sourcePreview: { index: 1, sessionId: 2, source },
        utilityPanel: "source",
      }),
    );

    expect(result.current.state.sourcePreview).toBeNull();
    expect(result.current.state.utilityPanel).toBeNull();
  });
});
