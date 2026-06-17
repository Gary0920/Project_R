import type { GeneratedFileResponse } from "../../shared/api/types";

export type EditableEmailDraft = {
  subject: string;
  body: string;
  from: string;
  to: string;
  cc: string;
  bcc: string;
};

export function isEmailDraftFile(file: GeneratedFileResponse) {
  const name = (file.filename || "").toLowerCase();
  const mime = (file.mime_type || "").toLowerCase();
  return Boolean(file.email_draft || name.endsWith(".eml") || mime.includes("message/rfc822"));
}

export function editableEmailDraft(file: GeneratedFileResponse): EditableEmailDraft {
  const draft = file.email_draft ?? {};
  return {
    subject: draft.subject ?? file.filename.replace(/\.eml$/i, ""),
    body: draft.body ?? "",
    from: addressText(draft.from),
    to: addressText(draft.to),
    cc: addressText(draft.cc),
    bcc: addressText(draft.bcc),
  };
}

export function emailDraftBodyForCopy(draft: EditableEmailDraft) {
  return draft.body.trim();
}

export function buildMailtoUrl(draft: EditableEmailDraft) {
  const params = new URLSearchParams();
  if (draft.subject.trim()) params.set("subject", draft.subject.trim());
  if (draft.body.trim()) params.set("body", draft.body.trim());
  if (draft.cc.trim()) params.set("cc", draft.cc.trim());
  if (draft.bcc.trim()) params.set("bcc", draft.bcc.trim());
  const to = encodeURIComponent(draft.to.trim());
  return `mailto:${to}${params.toString() ? `?${params.toString()}` : ""}`;
}

export function emailDraftSummary(file: GeneratedFileResponse) {
  const draft = editableEmailDraft(file);
  const body = draft.body.replace(/\s+/g, " ").trim();
  return {
    subject: draft.subject,
    bodyPreview: body.length > 140 ? `${body.slice(0, 140)}...` : body,
  };
}

export function buildEditedEmailDraftEml(draft: EditableEmailDraft) {
  const headers = [
    ["From", draft.from],
    ["To", draft.to],
    ["Cc", draft.cc],
    ["Bcc", draft.bcc],
    ["Subject", encodeHeaderValue(draft.subject.trim() || "Project_R 邮件草稿")],
    ["Date", new Date().toUTCString()],
    ["MIME-Version", "1.0"],
    ["Content-Type", 'text/plain; charset="UTF-8"'],
    ["Content-Transfer-Encoding", "8bit"],
  ]
    .filter(([, value]) => String(value ?? "").trim())
    .map(([name, value]) => `${name}: ${sanitizeHeaderValue(value)}`);
  return `${headers.join("\r\n")}\r\n\r\n${normalizeEmailBody(draft.body)}`;
}

export function editedEmailDraftFilename(file: GeneratedFileResponse, draft: EditableEmailDraft) {
  const source = draft.subject.trim() || file.filename.replace(/\.eml$/i, "") || "email-draft";
  const safeName = source
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
  return `${safeName || "email-draft"}.eml`;
}

function addressText(value: string | string[] | undefined) {
  if (Array.isArray(value)) return value.filter(Boolean).join(", ");
  return value ?? "";
}

function sanitizeHeaderValue(value: string | undefined) {
  return String(value ?? "").replace(/[\r\n]+/g, " ").trim();
}

function normalizeEmailBody(value: string) {
  return value.replace(/\r?\n/g, "\r\n").trimEnd();
}

function encodeHeaderValue(value: string) {
  const safeValue = sanitizeHeaderValue(value);
  if (/^[\x20-\x7e]*$/.test(safeValue)) return safeValue;
  const bytes = new TextEncoder().encode(safeValue);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return `=?UTF-8?B?${window.btoa(binary)}?=`;
}
