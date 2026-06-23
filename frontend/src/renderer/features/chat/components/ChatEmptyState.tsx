import { useMemo, useState } from "react";

import type { WorkspaceResponse } from "../../../shared/api/types";
import {
  ChatIcon,
  ChevronRightIcon,
  NoteIcon,
  PromptIcon,
  WorkspaceIcon,
} from "../../../shared/icons/LineIcons";
import type { Workspace } from "../../workspace/state";
import { getWorkspaceAffiliationLabel } from "../../workspace/workspaceAffiliation";
import { QUICK_START_PLACEHOLDERS } from "../quickStartConfig";
import { recordQuickStartUsage, sortQuickStartItems } from "../quickStartUsage";

export type ChatEmptyStateProps = {
  activeWorkspace?: WorkspaceResponse | null;
  isSplitPane?: boolean;
  mode?: "chat" | "agent" | string;
  onFocusComposer?: () => void;
};

export function ChatEmptyState({
  activeWorkspace,
  isSplitPane = false,
  mode = "chat",
  onFocusComposer,
}: ChatEmptyStateProps) {
  const [usageVersion, setUsageVersion] = useState(0);
  const sortedQuickStarts = useMemo(
    () => sortQuickStartItems(QUICK_START_PLACEHOLDERS),
    [usageVersion],
  );
  const modeLabel = mode === "agent" ? "Agent 模式" : "Chat 模式";
  const contextLabel = activeWorkspace
    ? `${getWorkspaceAffiliationLabel(activeWorkspace as Workspace)} · ${modeLabel}`
    : modeLabel;
  const quickStartIcons = {
    "placeholder-email-reply": <PromptIcon />,
    "placeholder-meeting-minutes": <NoteIcon />,
    "placeholder-drawing-extract": <WorkspaceIcon />,
    "placeholder-project-comm": <ChatIcon />,
  };

  if (isSplitPane) {
    return (
      <div className="empty-chat-v2 empty-chat-v2-compact">
        <div className="empty-chat-v2-copy">
          <h2>选择一个对话</h2>
          <p>先点击这个区域，再从左侧会话列表选择要放进来的对话。</p>
        </div>
      </div>
    );
  }

  function handleQuickStart(id: string) {
    recordQuickStartUsage(id);
    setUsageVersion((value) => value + 1);
    onFocusComposer?.();
  }

  return (
    <div className="empty-chat-v2">
      <div className="empty-chat-v2-copy">
        <h2>今天需要处理什么？</h2>
        <p>{contextLabel}</p>
      </div>
      <div className="empty-chat-quickstarts">
        {sortedQuickStarts.map((item) => (
          <button
            aria-label={`${item.label}：${item.description ?? "快速开始"}`}
            className="empty-chat-quickstart-btn"
            key={item.id}
            onClick={() => handleQuickStart(item.id)}
            type="button"
          >
            <span className="empty-chat-quickstart-icon">
              {quickStartIcons[item.id as keyof typeof quickStartIcons] ?? <PromptIcon />}
            </span>
            <span className="empty-chat-quickstart-copy">
              <strong>{item.label}</strong>
              {item.description ? <span>{item.description}</span> : null}
            </span>
            <ChevronRightIcon className="empty-chat-quickstart-arrow" />
          </button>
        ))}
      </div>
    </div>
  );
}
