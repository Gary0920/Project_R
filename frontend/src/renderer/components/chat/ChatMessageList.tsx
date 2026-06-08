import { useEffect, useState, type RefObject, type ReactNode } from "react";

import { fetchSessionAttachmentBlob } from "../../api/chat";
import type { ApiClientOptions } from "../../api/client";
import type {
  AgentRunResponse,
  ChatContextTraceResponse,
  ChatSourceResponse,
  GeneratedFileResponse,
  SessionAttachmentResponse,
  SkillRunResponse,
} from "../../api/types";
import type { ChatMessage } from "../../atoms/chat-atoms";
import { APP_NAME } from "../../constants/app";
import { AgentIcon, CopyIcon, EditIcon, RefreshIcon, TrashIcon, XmarkIcon } from "../LineIcons";

type SourcePreview = {
  index: number;
  source: ChatSourceResponse;
  sessionId?: number | null;
};

type AttachmentKind = "image" | "pdf" | "text" | "file";

function getAttachmentKind(fileName: string, contentType: string): AttachmentKind {
  const lowerName = fileName.toLowerCase();
  const lowerType = contentType.toLowerCase();
  if (lowerType.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(lowerName)) return "image";
  if (lowerType.includes("pdf") || lowerName.endsWith(".pdf")) return "pdf";
  if (lowerType.startsWith("text/") || /\.(txt|md|csv|json|log)$/i.test(lowerName)) return "text";
  return "file";
}

function formatAttachmentSize(size: number) {
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function attachmentSourceLabel(attachment: { source_label?: string; source_scope?: string }) {
  if (attachment.source_label) return attachment.source_label;
  if (attachment.source_scope === "workspace") return "工作区文件";
  if (attachment.source_scope === "local_private") return "本机文件";
  return "会话附件";
}

export type ChatMessageListController = Record<string, any> & {
  apiOptions: ApiClientOptions;
  copiedMessageId: number | null;
  currentUser: { avatar?: string; nickname?: string | null } | null;
  editingDraft: string;
  editingMessageId: number | null;
  isActivePane: boolean;
  isEmptySplitPane: boolean;
  messageActionBusyId: number | null;
  messages: ChatMessage[];
  paneSessionId: number | null;
  scrollRef: RefObject<HTMLDivElement | null>;
  serverUrl: string;
  sessionIsSending: boolean;
  token: string | null;
};

export type ChatMessageListProps = {
  controller: ChatMessageListController;
};

function markdownToPlainText(value: string) {
  return value
    .replace(/```[a-zA-Z0-9_-]*\n([\s\S]*?)```/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/[*_~]{1,3}/g, "")
    .trim();
}

export async function copyText(value: string, cleanMarkdown = false) {
  const text = cleanMarkdown ? markdownToPlainText(value) : value;
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Fall back to the legacy copy path below. Some embedded browsers deny Clipboard API.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!ok) {
    throw new Error("Clipboard copy failed");
  }
}

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

function generatedFileKindLabel(file: GeneratedFileResponse) {
  const mime = (file.mime_type || "").toLowerCase();
  const name = (file.filename || "").toLowerCase();
  if (mime.includes("word") || name.endsWith(".docx")) return "已生成 Word 文档";
  if (mime.includes("spreadsheet") || name.endsWith(".xlsx")) return "已生成 Excel 文件";
  if (mime.includes("presentation") || name.endsWith(".pptx")) return "已生成演示文稿";
  if (mime.includes("pdf") || name.endsWith(".pdf")) return "已生成 PDF 文件";
  return "已生成文件";
}

function renderGeneratedFileCard(file: GeneratedFileResponse, onDownload: (file: GeneratedFileResponse) => void) {
  return (
    <div className="message-file-card">
      <div>
        <strong>{file.filename}</strong>
        <span>{generatedFileKindLabel(file)}</span>
      </div>
      <button
        className="message-file-download"
        onClick={() => onDownload(file)}
        type="button"
      >
        下载
      </button>
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function isImageAttachmentResponse(attachment: SessionAttachmentResponse) {
  return (attachment.content_type || "").toLowerCase().startsWith("image/");
}

function attachmentKindLabel(attachment: SessionAttachmentResponse) {
  const kind = getAttachmentKind(attachment.original_name, attachment.content_type || "");
  if (kind === "image") return "IMG";
  if (kind === "pdf") return "PDF";
  if (kind === "text") return "TXT";
  return "FILE";
}

function MessageAttachments({
  attachments,
  apiOptions,
}: {
  attachments?: SessionAttachmentResponse[];
  apiOptions: ApiClientOptions;
}) {
  const visibleAttachments = attachments ?? [];
  if (!visibleAttachments.length) return null;
  return (
    <div className={`message-attachments ${visibleAttachments.length === 1 ? "is-single" : ""}`}>
      {visibleAttachments.map((attachment) =>
        isImageAttachmentResponse(attachment) ? (
          <MessageAttachmentImage attachment={attachment} apiOptions={apiOptions} key={attachment.id} />
        ) : (
          <MessageAttachmentFile attachment={attachment} apiOptions={apiOptions} key={attachment.id} />
        ),
      )}
    </div>
  );
}

function MessageAttachmentImage({
  attachment,
  apiOptions,
}: {
  attachment: SessionAttachmentResponse;
  apiOptions: ApiClientOptions;
}) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setImageUrl(null);
    setLoadFailed(false);
    fetchSessionAttachmentBlob(apiOptions, attachment.session_id, attachment.id, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setImageUrl(objectUrl);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setLoadFailed(true);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [apiOptions.baseUrl, apiOptions.token, apiOptions.onUnauthorized, attachment.id, attachment.session_id]);

  useEffect(() => {
    if (!previewOpen) return;
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setPreviewOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [previewOpen]);

  return (
    <>
      <button
        className={`message-attachment-image ${loadFailed ? "is-failed" : ""}`}
        disabled={!imageUrl}
        onClick={() => imageUrl ? setPreviewOpen(true) : undefined}
        title={imageUrl ? `点击预览图片 · ${attachmentSourceLabel(attachment)}` : attachment.original_name}
        type="button"
      >
        {imageUrl ? (
          <>
            <img alt={attachment.original_name} src={imageUrl} />
            <span className="message-attachment-image-source">{attachmentSourceLabel(attachment)}</span>
          </>
        ) : (
          <span>{loadFailed ? "图片加载失败" : "图片加载中"}</span>
        )}
      </button>
      {previewOpen && imageUrl ? (
        <div className="attachment-lightbox-backdrop" onClick={() => setPreviewOpen(false)} role="presentation">
          <div className="attachment-lightbox" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <button className="attachment-lightbox-close" onClick={() => setPreviewOpen(false)} title="关闭预览" type="button">
              <XmarkIcon />
            </button>
            <img alt={attachment.original_name} src={imageUrl} />
            <div className="attachment-lightbox-footer">
              <span>{attachment.original_name} · {attachmentSourceLabel(attachment)}</span>
              <button
                onClick={() => void fetchSessionAttachmentBlob(apiOptions, attachment.session_id, attachment.id)
                  .then((blob) => downloadBlob(blob, attachment.original_name))
                  .catch(() => {})}
                type="button"
              >
                下载
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function MessageAttachmentFile({
  attachment,
  apiOptions,
}: {
  attachment: SessionAttachmentResponse;
  apiOptions: ApiClientOptions;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const kind = getAttachmentKind(attachment.original_name, attachment.content_type || "");
  const canPreview = kind === "pdf" || kind === "text";
  const sourceLabel = attachmentSourceLabel(attachment);
  async function handleOpenAttachment() {
    setBusy(true);
    setFailed(false);
    try {
      const blob = await fetchSessionAttachmentBlob(apiOptions, attachment.session_id, attachment.id);
      if (canPreview) {
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank", "noopener,noreferrer");
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } else {
        downloadBlob(blob, attachment.original_name);
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      className="message-attachment-file"
      disabled={busy}
      onClick={() => void handleOpenAttachment()}
      title={failed ? "附件打开失败" : canPreview ? "打开预览" : "下载附件"}
      type="button"
    >
      <span className={`message-attachment-file-kind is-${kind}`}>{attachmentKindLabel(attachment)}</span>
      <span className="message-attachment-file-main">
        <strong>{attachment.original_name}</strong>
        <small>{failed ? "打开失败" : `${sourceLabel} · ${formatAttachmentSize(attachment.size)} · ${canPreview ? "打开预览" : "下载"}`}</small>
      </span>
    </button>
  );
}

function renderSourceRefTag(
  label: string,
  index: number,
  key: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const source = sources?.[index - 1];
  const title = source
    ? `${source.source_title || source.file}\n${source.section_path || source.file}\n${source.content.slice(0, 120)}`
    : `来源 ${index}`;
  return (
    <button
      className="message-source-ref"
      disabled={!source}
      key={key}
      onClick={() => source ? onSelectSource?.({ index, source }) : undefined}
      title={title}
      type="button"
    >
      {label.includes("Doc") ? label : `[${index}]`}
    </button>
  );
}

function renderInlineMarkdown(
  text: string,
  keyPrefix: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[\[[^\]]+\]\]|[（(]\s*来源\s*\d+\s*[）)]|来源\s*\d+)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}-strong-${match.index}`}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code className="message-inline-code" key={`${keyPrefix}-code-${match.index}`}>{token.slice(1, -1)}</code>);
    } else if (/来源\s*\d+/.test(token)) {
      const sourceIndex = Number(token.match(/\d+/)?.[0] ?? "0");
      nodes.push(renderSourceRefTag(`[${sourceIndex}]`, sourceIndex, `${keyPrefix}-source-${match.index}`, sources, onSelectSource));
    } else {
      nodes.push(<span className="message-wikilink" key={`${keyPrefix}-wiki-${match.index}`}>{token}</span>);
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function isMarkdownTable(lines: string[]) {
  return lines.length >= 2 && lines[0].includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[1]);
}

function renderMarkdownTable(
  lines: string[],
  key: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const parseRow = (line: string) => line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((cell) => cell.trim());
  const headers = parseRow(lines[0]);
  const rows = lines.slice(2).filter((line) => line.includes("|")).map(parseRow);
  return (
    <div className="message-table-wrap" key={key}>
      <table className="message-table">
        <thead>
          <tr>{headers.map((header, index) => <th key={`${key}-h-${index}`}>{renderInlineMarkdown(header, `${key}-h-${index}`, sources, onSelectSource)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${key}-r-${rowIndex}`}>
              {row.map((cell, cellIndex) => <td key={`${key}-r-${rowIndex}-${cellIndex}`}>{renderInlineMarkdown(cell, `${key}-r-${rowIndex}-${cellIndex}`, sources, onSelectSource)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderMarkdownText(
  text: string,
  keyPrefix: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const blocks = text.split(/\n{2,}/g).filter((block) => block.trim().length > 0);
  return blocks.map((block, blockIndex) => {
    const key = `${keyPrefix}-block-${blockIndex}`;
    const lines = block.split("\n").filter((line) => line.trim().length > 0);
    const firstLine = lines[0]?.trim() ?? "";

    if (isMarkdownTable(lines)) {
      return renderMarkdownTable(lines, key, sources, onSelectSource);
    }
    if (lines.every((line) => /^\s*-{3,}\s*$/.test(line))) {
      return <hr className="message-divider" key={key} />;
    }
    if (/^#{1,4}\s+/.test(firstLine)) {
      const level = Math.min(4, firstLine.match(/^#+/)?.[0].length ?? 3);
      const headingContent = renderInlineMarkdown(firstLine.replace(/^#{1,4}\s+/, ""), key, sources, onSelectSource);
      if (level === 1) return <h1 className="message-heading" key={key}>{headingContent}</h1>;
      if (level === 2) return <h2 className="message-heading" key={key}>{headingContent}</h2>;
      if (level === 3) return <h3 className="message-heading" key={key}>{headingContent}</h3>;
      return <h4 className="message-heading" key={key}>{headingContent}</h4>;
    }
    if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
      return (
        <ul className="message-list" key={key}>
          {lines.map((line, index) => <li key={`${key}-${index}`}>{renderInlineMarkdown(line.replace(/^\s*[-*]\s+/, ""), `${key}-${index}`, sources, onSelectSource)}</li>)}
        </ul>
      );
    }
    if (lines.every((line) => /^\s*\d+\.\s+/.test(line))) {
      return (
        <ol className="message-list" key={key}>
          {lines.map((line, index) => <li key={`${key}-${index}`}>{renderInlineMarkdown(line.replace(/^\s*\d+\.\s+/, ""), `${key}-${index}`, sources, onSelectSource)}</li>)}
        </ol>
      );
    }
    if (lines.every((line) => /^\s*>\s?/.test(line))) {
      return <blockquote className="message-quote" key={key}>{lines.map((line, index) => <p key={`${key}-${index}`}>{renderInlineMarkdown(line.replace(/^\s*>\s?/, ""), `${key}-${index}`, sources, onSelectSource)}</p>)}</blockquote>;
    }
    return (
      <p className="message-paragraph" key={key}>
        {lines.map((line, index) => (
          <span key={`${key}-${index}`}>
            {renderInlineMarkdown(line, `${key}-${index}`, sources, onSelectSource)}
            {index < lines.length - 1 ? <br /> : null}
          </span>
        ))}
      </p>
    );
  });
}

export function renderMessageContent(
  content: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const nodes: ReactNode[] = [];
  const pattern = /```([A-Za-z0-9_-]+)?\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = pattern.exec(content)) !== null) {
    const before = content.slice(lastIndex, match.index);
    if (before.trim()) {
      nodes.push(...renderMarkdownText(before, `text-${index}`, sources, onSelectSource));
    }
    const language = match[1]?.trim();
    const code = match[2].trim();
    nodes.push(
      <MessageCodeBlock code={code} key={`code-${index}`} language={language} />,
    );
    lastIndex = pattern.lastIndex;
    index += 1;
  }
  const rest = content.slice(lastIndex);
  if (rest.trim()) {
    nodes.push(...renderMarkdownText(rest, `text-${index}`, sources, onSelectSource));
  }
  return nodes;
}

function MessageCodeBlock({ code, language }: { code: string; language?: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (copyState === "idle") return;
    const timer = window.setTimeout(() => setCopyState("idle"), 1600);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  async function handleCopyCode() {
    try {
      await copyText(code);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <div className="message-code-block">
      <div className="message-code-toolbar">
        <span>{language || "可复制内容"}</span>
        <button
          className={`message-code-copy ${copyState !== "idle" ? `is-${copyState}` : ""}`}
          onClick={() => void handleCopyCode()}
          title={copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制"}
          type="button"
        >
          {copyState === "copied" ? <span className="message-action-check">✓</span> : <CopyIcon />}
          {copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制"}
        </button>
      </div>
      <pre className="message-code"><code>{code}</code></pre>
    </div>
  );
}

function renderSkillRunCard(
  skillRun: SkillRunResponse,
  options: {
    showGeneratedFile?: boolean;
    onDownloadGeneratedFile?: (file: GeneratedFileResponse) => void;
  } = {},
) {
  const missingFields = skillRun.missing_inputs
    .map((item) => String(item.label ?? item.name ?? "待补充字段"))
    .filter(Boolean);
  const dispatchSteps = Array.isArray(skillRun.dispatch?.steps) ? skillRun.dispatch.steps as Array<Record<string, unknown>> : [];
  return (
    <div className="message-skill-card">
      <div className="message-skill-header">
        <strong>{skillRun.skill?.display_name ?? skillRun.skill_name}</strong>
        <span>{skillRun.status === "completed" ? "已完成" : skillRun.status === "ready" ? "待执行" : skillRun.status === "failed" ? "失败" : "收集中"}</span>
      </div>
      {dispatchSteps.length ? (
        <div className="message-skill-dispatch">
          {dispatchSteps.map((step, index) => (
            <span key={`${String(step.id ?? index)}-${String(step.tool ?? "")}`}>
              {String(step.label ?? step.tool ?? "执行步骤")}
            </span>
          ))}
        </div>
      ) : null}
      {missingFields.length ? (
        <div className="message-skill-fields">
          {missingFields.map((field) => (
            <span key={field}>{field}</span>
          ))}
        </div>
      ) : null}
      {options.showGeneratedFile !== false && skillRun.generated_file && options.onDownloadGeneratedFile ? (
        renderGeneratedFileCard(skillRun.generated_file, options.onDownloadGeneratedFile)
      ) : skillRun.generated_file ? (
        <div className="message-skill-output">{skillRun.generated_file.filename}</div>
      ) : null}
    </div>
  );
}

function agentRunStatusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "waiting") return "等待输入";
  if (status === "queued") return "排队中";
  if (status === "cancelled") return "已取消";
  return "执行中";
}

function agentEventStatusLabel(status: string) {
  if (status === "completed") return "完成";
  if (status === "failed") return "失败";
  if (status === "waiting") return "等待";
  if (status === "queued") return "排队";
  return "进行中";
}

function renderAgentRunCard(agentRun: AgentRunResponse) {
  const events = agentRun.events ?? [];
  const completedEvents = events.filter((event) => event.status === "completed").length;
  const isPlanning = ["queued", "waiting"].includes(agentRun.status);
  const activeEvent = events.find((event) => event.status === "running" || event.status === "waiting")
    ?? events.find((event) => event.status === "queued")
    ?? events[events.length - 1];
  const failedEvent = events.find((event) => event.status === "failed");
  const progressPercent = events.length ? Math.round((completedEvents / events.length) * 100) : (agentRun.status === "completed" ? 100 : 0);
  const planSummary = events.length
    ? events.slice(0, 4).map((event) => event.title).join(" / ")
    : "等待后端返回执行步骤。";
  return (
    <div className={`message-agent-run-card is-${agentRun.status}`}>
      <div className="message-agent-run-header">
        <span className="message-agent-run-icon"><AgentIcon /></span>
        <div>
          <strong>{agentRun.title}</strong>
          <span>{isPlanning ? "计划模式" : agentRunStatusLabel(agentRun.status)}{events.length ? ` · 步骤 ${completedEvents}/${events.length}` : ""}</span>
        </div>
      </div>
      {events.length ? (
        <div className="message-agent-progress" aria-label={`执行进度 ${progressPercent}%`}>
          <span style={{ width: `${progressPercent}%` }} />
        </div>
      ) : null}
      <div className="message-agent-plan-grid">
        <section>
          <span>任务理解</span>
          <p>{agentRun.title || "Agent 正在理解本次任务目标。"}</p>
        </section>
        <section>
          <span>执行计划</span>
          <p>{planSummary}</p>
        </section>
      </div>
      {activeEvent || failedEvent ? (
        <div className={`message-agent-current-step ${failedEvent ? "is-failed" : ""}`}>
          <span>{failedEvent ? "失败位置" : "当前步骤"}</span>
          <strong>{(failedEvent ?? activeEvent)?.title}</strong>
          {(failedEvent ?? activeEvent)?.detail ? <p>{(failedEvent ?? activeEvent)?.detail}</p> : null}
        </div>
      ) : null}
      {isPlanning ? (
        <div className="message-agent-plan-actions">
          <button disabled type="button">确认执行</button>
          <button disabled type="button">修改计划</button>
          <small>当前后端尚未接入计划审批；此处只展示计划形态。</small>
        </div>
      ) : null}
      {events.length ? (
        <ol className="message-agent-event-list">
          {events.map((event) => (
            <li className={`message-agent-event is-${event.status}`} key={event.id}>
              <span className="message-agent-event-dot" />
              <div>
                <div className="message-agent-event-title">
                  <strong>{event.title}</strong>
                  <small>{agentEventStatusLabel(event.status)}</small>
                </div>
                {event.detail ? <p>{event.detail}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
      {agentRun.error_message ? <p className="message-agent-run-error">{agentRun.error_message}</p> : null}
    </div>
  );
}

function hasContextTrace(contextTrace: ChatContextTraceResponse | null | undefined) {
  if (!contextTrace) return false;
  return Boolean(
    contextTrace.attachments?.length ||
    contextTrace.knowledge?.source_count ||
    contextTrace.prompt?.selected_prompt_id ||
    contextTrace.prompt?.system_prompt_provided ||
    contextTrace.skill?.skill_name ||
    contextTrace.gbrain_think?.gap_count ||
    contextTrace.gbrain_think?.conflict_count ||
    contextTrace.gbrain_think?.warning_count ||
    contextTrace.model?.model,
  );
}

function renderContextTraceCard(
  contextTrace: ChatContextTraceResponse | null | undefined,
  options: { onSubmitGBrainThinkReview?: () => void; gbrainThinkReviewBusy?: boolean } = {},
) {
  if (!hasContextTrace(contextTrace) || !contextTrace) return null;
  const attachments = contextTrace.attachments ?? [];
  const sources = contextTrace.knowledge?.sources ?? [];
  const prompt = contextTrace.prompt;
  const model = contextTrace.model;
  const gbrainThink = contextTrace.gbrain_think;
  const gbrainGaps = gbrainThink?.gaps?.filter(Boolean) ?? [];
  const gbrainConflicts = gbrainThink?.conflicts?.filter(Boolean) ?? [];
  const gbrainWarnings = gbrainThink?.warnings?.filter(Boolean) ?? [];
  const modelBadges = [
    model?.model,
    model?.thinking ? "思考" : null,
    model?.web_search ? "联网搜索" : null,
  ].filter(Boolean).join(" · ");
  return (
    <div className="message-context-trace">
      <div className="message-context-trace-header">
        <strong>本轮上下文</strong>
        {modelBadges ? <span>{modelBadges}</span> : null}
      </div>
      <div className="message-context-trace-grid">
        {attachments.length ? (
          <div className="message-context-trace-section">
            <span>附件</span>
            {attachments.slice(0, 4).map((attachment) => (
              <small key={`${attachment.id}-${attachment.name}`}>{attachment.name ?? `附件 ${attachment.id}`}</small>
            ))}
            {attachments.length > 4 ? <small>另有 {attachments.length - 4} 个附件</small> : null}
          </div>
        ) : null}
        {sources.length || contextTrace.knowledge?.source_count ? (
          <div className="message-context-trace-section">
            <span>知识来源</span>
            {sources.slice(0, 4).map((source) => (
              <small key={`${source.index}-${source.file}`}>{source.section_path || source.source_title || source.file}</small>
            ))}
            {(contextTrace.knowledge?.source_count ?? 0) > sources.length ? (
              <small>共 {contextTrace.knowledge?.source_count} 个来源</small>
            ) : null}
          </div>
        ) : null}
        {gbrainThink && (gbrainGaps.length || gbrainConflicts.length || gbrainWarnings.length) ? (
          <div className="message-context-trace-section is-gbrain-think">
            <span>
              GBrain 推理状态
              {options.onSubmitGBrainThinkReview ? (
                <button
                  className="message-context-trace-action"
                  disabled={options.gbrainThinkReviewBusy}
                  onClick={options.onSubmitGBrainThinkReview}
                  type="button"
                >
                  {options.gbrainThinkReviewBusy ? "提交中" : "提交审核"}
                </button>
              ) : null}
            </span>
            {gbrainConflicts.length ? <small className="is-conflict">冲突 {gbrainConflicts.length} 条</small> : null}
            {gbrainGaps.length ? <small className="is-gap">缺口 {gbrainGaps.length} 条</small> : null}
            {gbrainWarnings.length ? <small className="is-warning">警告 {gbrainWarnings.length} 条</small> : null}
          </div>
        ) : null}
        {(prompt?.selected_prompt_id || prompt?.system_prompt_provided || contextTrace.skill?.skill_name) ? (
          <div className="message-context-trace-section">
            <span>提示词 / Skill</span>
            {prompt?.selected_prompt_id ? <small>{prompt.selected_prompt_id}</small> : null}
            {contextTrace.skill?.display_name || contextTrace.skill?.skill_name ? (
              <small>{contextTrace.skill.display_name || contextTrace.skill.skill_name}</small>
            ) : null}
            {prompt?.system_prompt_provided ? <small>{prompt.system_prompt_preview || "已使用会话提示词"}</small> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}


export function ChatMessageList({ controller }: ChatMessageListProps) {
  const {
    activeWorkspace,
    apiOptions,
    copiedMessageId,
    currentUser,
    editingDraft,
    editingMessageId,
    formatClockTime,
    handleActivateVersion,
    handleCopyMessage,
    handleSubmitEditedMessage,
    handleSubmitGBrainThinkReview,
    handleSwitchToAgent,
    isActivePane,
    isEmptySplitPane,
    messageActionBusyId,
    messages,
    mode,
    openFeedbackDialog,
    openRegenerateDialog,
    paneSessionId,
    renderAvatar,
    requestDeleteMessageContext,
    scrollRef,
    serverUrl,
    sessionIsSending,
    setEditingDraft,
    setEditingMessageId,
    setSourcePreview,
    setUtilityPanel,
    sideBySideOpen,
    startEditingMessage,
    token,
  } = controller;

  function getLoadingProcessSteps(isInline = false) {
    if (mode === "agent") {
      return isInline
        ? ["正在整理执行步骤", "正在更新任务状态", "正在生成结果"]
        : ["正在理解任务目标", "正在整理执行计划", "正在准备步骤状态"];
    }
    const latestUserMessage = [...messages].reverse().find((message) => message.role === "user") as any;
    const latestContent = String(latestUserMessage?.content ?? "").trim();
    const hasAttachments = Array.isArray(latestUserMessage?.attachments) && latestUserMessage.attachments.length > 0;
    if (latestContent.startsWith("/query")) {
      return ["正在识别知识库问题", "正在确认查询范围", "正在生成回答"];
    }
    if (hasAttachments) {
      return ["正在读取本轮附件", "正在整理上下文", "正在生成回答"];
    }
    return ["正在理解问题", "正在整理上下文", "正在生成回答"];
  }

  function LoadingPlaceholder() {
    const [stepIndex, setStepIndex] = useState(0);
    const processSteps = getLoadingProcessSteps();

    useEffect(() => {
      const interval = window.setInterval(() => {
        setStepIndex((value) => (value + 1) % processSteps.length);
      }, 2000);
      return () => window.clearInterval(interval);
    }, [processSteps.length]);

    return (
      <article className="message-row message-row-assistant message-row-loading">
        <span className="message-avatar assistant-avatar is-text">R</span>
        <div className="message-body">
          <div className="message-meta">
            <div className="message-name-line">
              <span className="message-role-label">{APP_NAME}</span>
            </div>
          </div>
          <div className="message-bubble">
            <div className="loading-placeholder-inner">
              <svg className="pl" viewBox="0 0 128 128" width="128" height="128" xmlns="http://www.w3.org/2000/svg">
                <circle className="pl__ring pl__ring--a" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
                <circle className="pl__ring pl__ring--b" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
                <circle className="pl__ring pl__ring--c" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
                <circle className="pl__ring pl__ring--d" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
              </svg>
              <span className="loading-placeholder-text">{mode === "agent" ? "Agent 执行中" : "正在回复"}</span>
              <small className="loading-process-text">{processSteps[stepIndex]}</small>
            </div>
          </div>
        </div>
      </article>
    );
  }

  function InlineLoadingPlaceholder() {
    const [stepIndex, setStepIndex] = useState(0);
    const processSteps = getLoadingProcessSteps(true);

    useEffect(() => {
      const interval = window.setInterval(() => {
        setStepIndex((value) => (value + 1) % processSteps.length);
      }, 2000);
      return () => window.clearInterval(interval);
    }, [processSteps.length]);

    return (
      <div className="loading-placeholder-inner loading-placeholder-inline">
        <svg className="pl" viewBox="0 0 128 128" width="128" height="128" xmlns="http://www.w3.org/2000/svg">
          <circle className="pl__ring pl__ring--a" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
          <circle className="pl__ring pl__ring--b" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
          <circle className="pl__ring pl__ring--c" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
          <circle className="pl__ring pl__ring--d" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
        </svg>
        <span className="loading-placeholder-text">{mode === "agent" ? "执行中" : "生成中"}</span>
        <small className="loading-process-text">{processSteps[stepIndex]}</small>
      </div>
    );
  }

  function renderEmptyState(isSplitPane: boolean) {
    if (isSplitPane) {
      return (
        <div className="empty-chat empty-chat-compact">
          <span className="empty-chat-mark">R</span>
          <h2>选择一个对话</h2>
          <p>先点击这个区域，再从左侧会话列表选择要放进来的对话。</p>
        </div>
      );
    }
    if (mode === "agent") {
      return (
        <div className={`empty-agent ${sideBySideOpen ? "is-split-mode" : ""}`}>
          <div className="empty-agent-copy">
            <span className="empty-chat-mark">R</span>
            <h2>{activeWorkspace ? `在「${activeWorkspace.name}」开始 Agent` : "选择项目后开始 Agent"}</h2>
            <p>直接说明你要整理、核对或生成的业务结果。</p>
          </div>
        </div>
      );
    }
    return (
      <div className="empty-chat">
        <span className="empty-chat-mark">R</span>
        <h2>{activeWorkspace ? `在「${activeWorkspace.name}」开始聊天` : "从一个问题开始"}</h2>
        <p>询问规范、整理资料，或把当前工作流交给 Project_R 梳理成可执行步骤。</p>
      </div>
    );
  }

  function renderMessageVersionBar(message: ChatMessage) {
    const versions = message.versions?.length ? message.versions : [];
    if (versions.length <= 1) return null;
    const activeIndex = Math.max(0, versions.findIndex((version) => version.active_version || version.id === message.id));
    const previous = versions[Math.max(0, activeIndex - 1)];
    const next = versions[Math.min(versions.length - 1, activeIndex + 1)];
    const isBusy = messageActionBusyId === message.id;
    return (
      <div className="message-version-bar">
        <button
          className="message-version-btn"
          disabled={activeIndex <= 0 || isBusy}
          onClick={() => previous ? void handleActivateVersion(message, previous) : undefined}
          type="button"
        >
          &lt;
        </button>
        <span>{activeIndex + 1} / {versions.length}</span>
        <button
          className="message-version-btn"
          disabled={activeIndex >= versions.length - 1 || isBusy}
          onClick={() => next ? void handleActivateVersion(message, next) : undefined}
          type="button"
        >
          &gt;
        </button>
      </div>
    );
  }

  function renderMessageCard(message: ChatMessage) {
    const isEditing = editingMessageId === message.id;
    const isBusy = messageActionBusyId === message.id;
    const hasMessageBubble = Boolean(message.content.trim()) || Boolean(message.isTyping) || Boolean(message.isRegenerating);
    return (
      <article className={`message-row message-row-${message.role} ${message.status === "failed" ? "message-row-failed" : ""}`} key={message.id}>
        {message.role === "assistant" ? (
          <span className="message-avatar assistant-avatar is-text">R</span>
        ) : (
          renderAvatar(currentUser?.avatar, currentUser?.nickname, 30, serverUrl)
        )}
        <div className="message-body">
          <div className="message-meta">
            <div className="message-name-line">
              <span className="message-role-label">{message.role === "user" ? currentUser?.nickname ?? "你" : APP_NAME}</span>
              {message.role === "assistant" && message.model ? <span className="model-badge">{message.model}</span> : null}
              <time className="message-time">{formatClockTime(message.created_at)}</time>
            </div>
          </div>
          {isEditing ? (
            <div className="message-edit-box">
              <textarea
                autoFocus
                onChange={(event) => setEditingDraft(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                    event.preventDefault();
                    void handleSubmitEditedMessage(message);
                  }
                  if (event.key === "Escape") {
                    setEditingMessageId(null);
                    setEditingDraft("");
                  }
                }}
                value={editingDraft}
              />
              <div className="message-edit-actions">
                <span>Ctrl + Enter 提交</span>
                <button className="btn-secondary" onClick={() => {
                  setEditingMessageId(null);
                  setEditingDraft("");
                }} type="button">取消</button>
                <button className="btn-primary" disabled={isBusy || !editingDraft.trim()} onClick={() => void handleSubmitEditedMessage(message)} type="button">
                  提交
                </button>
              </div>
            </div>
          ) : (
            <>
              <MessageAttachments attachments={message.attachments} apiOptions={apiOptions} />
              {hasMessageBubble ? (
                <div className="message-bubble">
                  {message.isRegenerating ? (
                    <InlineLoadingPlaceholder />
                  ) : (
                    renderMessageContent(message.content, message.sources ?? [], (preview) => {
                      setSourcePreview({ ...preview, sessionId: message.session_id });
                      setUtilityPanel("source");
                    })
                  )}
                  {message.isTyping && !message.isRegenerating ? <span className="typing-caret" /> : null}
                </div>
              ) : null}
            </>
          )}
          {renderMessageVersionBar(message)}
          {message.sources?.length ? (
            <div className="message-sources is-compact">
              <span className="message-sources-title">引用来源：</span>
              {message.sources.map((source, index) => (
                <button
                  className="message-source-item"
                  key={`${source.file}-${index}`}
                  onClick={() => {
                    setSourcePreview({ index: index + 1, source, sessionId: message.session_id });
                    setUtilityPanel("source");
                  }}
                  type="button"
                >
                  <span className="message-source-index">[{index + 1}]</span>
                  <span className="message-source-path">{source.section_path || source.source_title || source.file}</span>
                  <span className="message-source-file">{source.file}</span>
                </button>
              ))}
            </div>
          ) : null}
          {message.role === "assistant" ? renderContextTraceCard(message.context_trace, {
            gbrainThinkReviewBusy: messageActionBusyId === message.id,
            onSubmitGBrainThinkReview: message.context_trace?.gbrain_think
              ? () => void handleSubmitGBrainThinkReview(message)
              : undefined,
          }) : null}
          {message.generated_file ? (
            renderGeneratedFileCard(
              message.generated_file,
              (file) => void downloadGeneratedFile(serverUrl, token, file),
            )
          ) : null}
          {message.agent_run ? renderAgentRunCard(message.agent_run) : null}
          {message.skill_run ? renderSkillRunCard(message.skill_run, {
            showGeneratedFile: !message.generated_file,
            onDownloadGeneratedFile: (file) => void downloadGeneratedFile(serverUrl, token, file),
          }) : null}
          {message.agent_suggestion ? (
            <div className="message-agent-suggestion">
              <div className="message-agent-suggestion-copy">
                <strong>建议切换到 Agent</strong>
                <span>{message.agent_suggestion.reason}</span>
              </div>
              <button
                className="message-agent-suggestion-btn"
                onClick={() => handleSwitchToAgent(message.id)}
                type="button"
              >
                <AgentIcon />
                <span>切换</span>
              </button>
            </div>
          ) : null}
          {message.role === "assistant" && message.feedback_rating ? (
            <div className="message-feedback-status">
              <span>已评分 {message.feedback_rating}/5</span>
              {message.feedback_comment ? <small>含意见</small> : null}
            </div>
          ) : null}
          <div className={`message-actions ${copiedMessageId === message.id ? "has-copy-success" : ""}`}>
            <button
              className={`message-action-btn ${copiedMessageId === message.id ? "is-copied" : ""}`}
              onClick={() => void handleCopyMessage(message)}
              title={copiedMessageId === message.id ? "已复制" : "复制"}
              type="button"
            >
              {copiedMessageId === message.id ? <span className="message-action-check">✓</span> : <CopyIcon />}
            </button>
            {message.role === "assistant" ? (
              <button
                className="message-action-btn"
                disabled={message.isOptimistic || isBusy}
                onClick={() => openRegenerateDialog(message)}
                title="重新生成"
                type="button"
              >
                <RefreshIcon />
              </button>
            ) : null}
            {message.role === "user" ? (
              <button
                className="message-action-btn"
                disabled={message.isOptimistic || isBusy}
                onClick={() => startEditingMessage(message)}
                title="编辑并开启新分支"
                type="button"
              >
                <EditIcon />
              </button>
            ) : null}
            {message.role === "assistant" ? (
              <button className="message-action-btn" onClick={() => handleSwitchToAgent(message.id)} title="切换到 Agent" type="button"><AgentIcon /></button>
            ) : null}
            {message.role === "assistant" ? (
              <button
                className={`message-action-btn ${message.feedback_rating ? "is-rated" : ""}`}
                disabled={message.isOptimistic || isBusy}
                onClick={() => openFeedbackDialog(message)}
                title="评分与意见"
                type="button"
              >
                <span className="message-action-star">★</span>
              </button>
            ) : null}
            <button
              className="message-action-btn"
              disabled={message.isOptimistic || isBusy}
              onClick={() => requestDeleteMessageContext(message)}
              title="删除当前问答"
              type="button"
            >
              <TrashIcon />
            </button>
          </div>
          {message.status === "failed" ? <p className="message-error">AI 服务暂时不可用</p> : null}
        </div>
      </article>
    );
  }

  return (
    <div className="message-scroll" ref={isActivePane ? scrollRef : undefined}>
      {messages.length === 0 ? renderEmptyState(isEmptySplitPane) : null}
      {messages.map(renderMessageCard)}
      {paneSessionId && sessionIsSending ? <LoadingPlaceholder /> : null}
    </div>
  );
}
