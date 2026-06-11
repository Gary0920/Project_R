import type { ChatSessionResponse } from "../../shared/api/types";
import { parseApiDate } from "../../shared/utils/time";

export function formatClockTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parseApiDate(value));
}

export function formatSidebarTime(value: string) {
  const date = parseApiDate(value);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  if (diffMs < 0) return "刚刚";

  const diffMinutes = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMinutes < 60) {
    return diffMinutes <= 0 ? "刚刚" : `${diffMinutes}分钟`;
  }
  if (diffHours < 24) {
    return `${diffHours}小时`;
  }
  if (diffDays < 7) {
    return `${diffDays}天`;
  }
  return "1周";
}

export function groupSessionsByTime(sessions: ChatSessionResponse[]) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400_000;

  const today: ChatSessionResponse[] = [];
  const yesterday: ChatSessionResponse[] = [];
  const earlier: ChatSessionResponse[] = [];

  for (const session of sessions) {
    const d = parseApiDate(session.updated_at);
    const dayStart = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    if (dayStart === startOfToday) {
      today.push(session);
    } else if (dayStart === startOfYesterday) {
      yesterday.push(session);
    } else {
      earlier.push(session);
    }
  }

  const groups: { key: string; label: string | null; items: ChatSessionResponse[] }[] = [];
  if (today.length) groups.push({ key: "today", label: "今天", items: today });
  if (yesterday.length) groups.push({ key: "yesterday", label: "昨天", items: yesterday });
  if (earlier.length) groups.push({ key: "earlier", label: "更早", items: earlier });
  return groups;
}

export function makeSessionTitle(content: string) {
  const compact = content
    .replace(/^\s*\/query\s+/i, "")
    .replace(/^\s*\/[A-Za-z0-9_-]+\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!compact) return "新对话";
  return compact.length > 24 ? `${compact.slice(0, 24)}...` : compact;
}

export function formatSessionDisplayTitle(title: string) {
  const compact = title
    .replace(/^\s*\/query\s+/i, "")
    .replace(/^\s*\/[A-Za-z0-9_-]+\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
  return compact || title;
}

export function getInitials(name: string | undefined | null) {
  const trimmed = name?.trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : "U";
}

export function resolveAvatarUrl(baseUrl: string, avatar: string | undefined | null) {
  if (!avatar) return "";
  if (avatar.startsWith("http") || avatar.startsWith("data:")) return avatar;
  if (avatar.startsWith("/")) return `${baseUrl.replace(/\/$/, "")}${avatar}`;
  return "";
}

export function renderAvatar(avatar: string | undefined, nickname: string | undefined | null, size = 22, baseUrl = "") {
  const imageUrl = resolveAvatarUrl(baseUrl, avatar);
  return (
    <span
      className={`message-avatar ${!imageUrl && !avatar ? "is-text" : ""}`}
      style={{ width: size, height: size, fontSize: size * 0.55 }}
    >
      {imageUrl ? (
        <img src={imageUrl} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      ) : (
        avatar || getInitials(nickname)
      )}
    </span>
  );
}
