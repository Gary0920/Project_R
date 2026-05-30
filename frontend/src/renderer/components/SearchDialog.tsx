import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { ChatSearchResultResponse, ChatSessionResponse } from "../api/types";

export type SearchResult = ChatSessionResponse & {
  workspace_name?: string;
  matched_message?: string | null;
};

export type SearchDialogProps = {
  sessions: SearchResult[];
  results?: ChatSearchResultResponse[];
  searchTerm: string;
  onSearchChange: (value: string) => void;
  onSelect: (sessionId: number) => void;
  onClose: () => void;
};

export function SearchDialog({ sessions, results, searchTerm, onSearchChange, onSelect, onClose }: SearchDialogProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [selectedIdx, setSelectedIdx] = useState(0);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    setSelectedIdx(0);
  }, [searchTerm]);

  const filtered = results ?? (searchTerm
    ? sessions.filter((s) => s.title.toLowerCase().includes(searchTerm.toLowerCase()))
    : sessions);

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && filtered[selectedIdx]) {
      onSelect(filtered[selectedIdx].id);
      onClose();
    }
  }

  return (
    <div className="search-dialog-backdrop" onClick={onClose}>
      <div className="search-dialog" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="search-dialog-input"
          placeholder="搜索对话标题和消息内容..."
          value={searchTerm}
          onChange={(e) => onSearchChange(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="search-dialog-results">
          {filtered.length === 0 ? (
            <div className="search-dialog-empty">
              {searchTerm ? "未找到匹配的对话" : "暂无对话"}
            </div>
          ) : (
            filtered.map((s, i) => (
              <div
                className="search-result-item"
                key={s.id}
                style={{ background: i === selectedIdx ? "hsl(var(--accent))" : undefined }}
                onClick={() => {
                  onSelect(s.id);
                  onClose();
                }}
              >
                <span className="search-result-title">{s.title}</span>
                <span className="search-result-preview">
                  {getPreviewText(s)}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function getPreviewText(result: ChatSearchResultResponse | SearchResult) {
  if ("matched_message" in result && result.matched_message) {
    return result.matched_message;
  }
  const workspaceName = "workspace_name" in result ? result.workspace_name : "";
  return `${workspaceName ? `${workspaceName} · ` : ""}${formatTime(result.updated_at)}`;
}
