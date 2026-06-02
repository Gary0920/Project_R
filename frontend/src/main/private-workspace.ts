import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, extname, join, relative, resolve } from "node:path";

export type PrivateWorkspaceConfig = {
  rootPath: string;
  isDefault: boolean;
  updatedAt: string;
};

export type PrivateWorkspaceAuthorizationStatus = "pending" | "authorized" | "uploaded";

export type PrivateWorkspaceFileRecord = {
  id: string;
  relativePath: string;
  fileName: string;
  contentType: string;
  size: number;
  sha256: string;
  updatedAt: string;
  sourceLabel: string;
  lastAuthorizationStatus: PrivateWorkspaceAuthorizationStatus;
  createdAt: string;
};

export type PrivateWorkspacePreprocessResult = {
  fileId: string;
  fileName: string;
  kind: "text" | "pdf" | "image" | "file";
  extractionStatus:
    | "text_excerpt_ready"
    | "pdf_text_ready"
    | "pdf_text_unavailable"
    | "image_preview_ready"
    | "metadata_only";
  sendForm: "excerpt" | "original_file" | "metadata_only";
  targetDefault: "chat_session" | "agent_temp_file";
  summary: string;
  excerpt: string | null;
  warnings: string[];
  localOnly: boolean;
};

export type PrivateWorkspaceFilePayload = PrivateWorkspaceFileRecord & {
  base64: string;
  preprocess: PrivateWorkspacePreprocessResult;
};

export type PrivateWorkspaceWorkerStatus = {
  status: "available" | "unavailable";
  available: boolean;
  rootPath: string | null;
  authorizedRoot: string | null;
  configPath: string;
  manifestPath: string;
  fileCount: number;
  supportedParsingTypes: string[];
  capabilities: {
    quickDrop: boolean;
    choosePrivateFiles: boolean;
    textExcerpt: boolean;
    readablePdfText: boolean;
    imagePreview: boolean;
    sendAuthorization: boolean;
    saveToProjectCopy: boolean;
  };
  lastError: string | null;
  checkedAt: string;
};

export type PrivateWorkspaceServicePaths = {
  userDataDir: string;
  documentsDir: string;
};

const PRIVATE_WORKSPACE_DIRS = [
  "00-Inbox-快捷投放",
  "01-对话文件",
  "02-固定资料",
  "03-生成草稿",
] as const;
const LOCAL_TEXT_EXCERPT_CHARS = 12000;
const SUMMARY_CHARS = 260;

export function createPrivateWorkspaceService(paths: PrivateWorkspaceServicePaths) {
  function getConfigPath() {
    return join(paths.userDataDir, "private-workspace", "config.json");
  }

  function getManifestPath() {
    return join(paths.userDataDir, "private-workspace", "manifest.json");
  }

  function getDefaultRoot() {
    return join(paths.documentsDir, "Project_R", "私人空间");
  }

  function ensureRoot(rootPath: string) {
    mkdirSync(rootPath, { recursive: true });
    for (const directory of PRIVATE_WORKSPACE_DIRS) {
      mkdirSync(join(rootPath, directory), { recursive: true });
    }
    return rootPath;
  }

  function writeConfig(config: PrivateWorkspaceConfig) {
    const configPath = getConfigPath();
    mkdirSync(dirname(configPath), { recursive: true });
    writeFileSync(configPath, JSON.stringify(config, null, 2), "utf-8");
  }

  function readConfig(): PrivateWorkspaceConfig {
    const defaultRoot = getDefaultRoot();
    const configPath = getConfigPath();
    if (!existsSync(configPath)) {
      const config = {
        rootPath: ensureRoot(defaultRoot),
        isDefault: true,
        updatedAt: new Date().toISOString(),
      };
      writeConfig(config);
      return config;
    }
    try {
      const parsed = JSON.parse(readFileSync(configPath, "utf-8")) as Partial<PrivateWorkspaceConfig>;
      const rootPath = typeof parsed.rootPath === "string" && parsed.rootPath.trim()
        ? parsed.rootPath
        : defaultRoot;
      const config = {
        rootPath: ensureRoot(rootPath),
        isDefault: resolve(rootPath) === resolve(defaultRoot),
        updatedAt: typeof parsed.updatedAt === "string" ? parsed.updatedAt : new Date().toISOString(),
      };
      if (config.rootPath !== parsed.rootPath || config.isDefault !== parsed.isDefault) {
        writeConfig(config);
      }
      return config;
    } catch {
      const config = {
        rootPath: ensureRoot(defaultRoot),
        isDefault: true,
        updatedAt: new Date().toISOString(),
      };
      writeConfig(config);
      return config;
    }
  }

  function setRoot(rootPath: string): PrivateWorkspaceConfig {
    const normalized = rootPath.trim();
    if (!normalized) {
      throw new Error("本机文件处理目录不能为空");
    }
    const config = {
      rootPath: ensureRoot(normalized),
      isDefault: resolve(normalized) === resolve(getDefaultRoot()),
      updatedAt: new Date().toISOString(),
    };
    writeConfig(config);
    return config;
  }

  function readManifest(): PrivateWorkspaceFileRecord[] {
    const manifestPath = getManifestPath();
    if (!existsSync(manifestPath)) {
      return [];
    }
    try {
      const parsed = JSON.parse(readFileSync(manifestPath, "utf-8")) as PrivateWorkspaceFileRecord[];
      return parsed.filter((item) => item.id && item.relativePath && item.fileName);
    } catch {
      return [];
    }
  }

  function writeManifest(items: PrivateWorkspaceFileRecord[]) {
    const manifestPath = getManifestPath();
    mkdirSync(dirname(manifestPath), { recursive: true });
    writeFileSync(manifestPath, JSON.stringify(items, null, 2), "utf-8");
  }

  function manifestRecordForPath(path: string, rootPath: string, existing?: PrivateWorkspaceFileRecord): PrivateWorkspaceFileRecord {
    const stats = statSync(path);
    const relativePath = relative(rootPath, path).replace(/\\/g, "/");
    const now = new Date().toISOString();
    return {
      id: existing?.id ?? `pw-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      relativePath,
      fileName: basename(path),
      contentType: contentTypeForFile(path),
      size: stats.size,
      sha256: hashFileSha256(path),
      updatedAt: stats.mtime.toISOString(),
      sourceLabel: "本机选择",
      lastAuthorizationStatus: existing?.lastAuthorizationStatus ?? "pending",
      createdAt: existing?.createdAt ?? now,
    };
  }

  function upsertRecords(records: PrivateWorkspaceFileRecord[]) {
    const current = readManifest();
    const nextByPath = new Map(current.map((item) => [item.relativePath, item]));
    for (const record of records) {
      nextByPath.set(record.relativePath, record);
    }
    const next = Array.from(nextByPath.values()).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    writeManifest(next);
    return next;
  }

  function copyFilesToInbox(filePaths: string[]) {
    const config = readConfig();
    const inbox = join(config.rootPath, "00-Inbox-快捷投放");
    mkdirSync(inbox, { recursive: true });
    const records: PrivateWorkspaceFileRecord[] = [];
    for (const filePath of filePaths) {
      const stats = statSync(filePath);
      if (!stats.isFile()) continue;
      const destination = dedupeDestinationPath(inbox, basename(filePath));
      copyFileSync(filePath, destination);
      records.push(manifestRecordForPath(destination, config.rootPath));
    }
    upsertRecords(records);
    return records;
  }

  function readFilePayloads(filePaths: string[]) {
    const manifest = readManifest();
    const records: PrivateWorkspaceFilePayload[] = [];
    const updatedRecords: PrivateWorkspaceFileRecord[] = [];
    for (const filePath of filePaths) {
      const stats = statSync(filePath);
      if (!stats.isFile()) continue;
      const sha256 = hashFileSha256(filePath);
      const relativePath = `本机选择/${sha256.slice(0, 12)}-${safePrivateWorkspaceFilename(basename(filePath))}`;
      const existing = manifest.find((item) => item.relativePath === relativePath);
      const record: PrivateWorkspaceFileRecord = {
        id: existing?.id ?? `pw-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
        relativePath,
        fileName: basename(filePath),
        contentType: contentTypeForFile(filePath),
        size: stats.size,
        sha256,
        updatedAt: stats.mtime.toISOString(),
        sourceLabel: "本机选择",
        lastAuthorizationStatus: existing?.lastAuthorizationStatus ?? "pending",
        createdAt: existing?.createdAt ?? new Date().toISOString(),
      };
      updatedRecords.push(record);
      records.push({
        ...record,
        base64: readFileSync(filePath).toString("base64"),
        preprocess: preprocessFile(filePath, record),
      });
    }
    if (updatedRecords.length) upsertRecords(updatedRecords);
    return records;
  }

  function setAuthorization(ids: string[], status: PrivateWorkspaceAuthorizationStatus) {
    const items = readManifest();
    const idSet = new Set(ids);
    const next = items.map((item) => idSet.has(item.id) ? { ...item, lastAuthorizationStatus: status } : item);
    writeManifest(next);
    return next;
  }

  function getWorkerStatus(): PrivateWorkspaceWorkerStatus {
    const checkedAt = new Date().toISOString();
    const configPath = getConfigPath();
    const manifestPath = getManifestPath();
    try {
      const config = readConfig();
      const manifest = readManifest();
      return {
        status: "available",
        available: true,
        rootPath: config.rootPath,
        authorizedRoot: config.rootPath,
        configPath,
        manifestPath,
        fileCount: manifest.length,
        supportedParsingTypes: ["markdown", "txt", "readable_pdf_text", "image_preview", "metadata"],
        capabilities: {
          quickDrop: true,
          choosePrivateFiles: true,
          textExcerpt: true,
          readablePdfText: true,
          imagePreview: true,
          sendAuthorization: true,
          saveToProjectCopy: true,
        },
        lastError: null,
        checkedAt,
      };
    } catch (error) {
      return {
        status: "unavailable",
        available: false,
        rootPath: null,
        authorizedRoot: null,
        configPath,
        manifestPath,
        fileCount: 0,
        supportedParsingTypes: [],
        capabilities: {
          quickDrop: false,
          choosePrivateFiles: false,
          textExcerpt: false,
          readablePdfText: false,
          imagePreview: false,
          sendAuthorization: false,
          saveToProjectCopy: false,
        },
        lastError: error instanceof Error ? error.message : "Local private workspace unavailable",
        checkedAt,
      };
    }
  }

  return {
    getConfigPath,
    getManifestPath,
    getDefaultRoot,
    ensureRoot,
    readConfig,
    setRoot,
    readManifest,
    writeManifest,
    copyFilesToInbox,
    readFilePayloads,
    setAuthorization,
    getWorkerStatus,
  };
}

export function isPathInside(parent: string, child: string) {
  const parentPath = resolve(parent);
  const childPath = resolve(child);
  const rel = relative(parentPath, childPath);
  return rel === "" || Boolean(rel && !rel.startsWith("..") && !rel.startsWith("/") && !rel.startsWith("\\") && !/^[a-zA-Z]:/.test(rel));
}

export function safePrivateWorkspaceFilename(filename: string) {
  const name = basename(filename).trim().replace(/[<>:"/\\|?*\x00-\x1F]/g, "_");
  return name.slice(0, 160) || "file";
}

export function contentTypeForFile(filename: string) {
  const suffix = extname(filename).toLowerCase();
  const map: Record<string, string> = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".log": "text/plain",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  };
  return map[suffix] ?? "application/octet-stream";
}

function dedupeDestinationPath(directory: string, filename: string) {
  const cleanName = safePrivateWorkspaceFilename(filename);
  const extension = extname(cleanName);
  const stem = extension ? cleanName.slice(0, -extension.length) : cleanName;
  let candidate = join(directory, cleanName);
  let index = 1;
  while (existsSync(candidate)) {
    candidate = join(directory, `${stem} (${index})${extension}`);
    index += 1;
  }
  return candidate;
}

function hashFileSha256(path: string) {
  const hash = createHash("sha256");
  hash.update(readFileSync(path));
  return hash.digest("hex");
}

function preprocessFile(path: string, record: PrivateWorkspaceFileRecord): PrivateWorkspacePreprocessResult {
  const suffix = extname(record.fileName).toLowerCase();
  if (isTextLike(record.contentType, suffix)) {
    const text = readTextExcerpt(path);
    return {
      fileId: record.id,
      fileName: record.fileName,
      kind: "text",
      extractionStatus: "text_excerpt_ready",
      sendForm: "excerpt",
      targetDefault: "chat_session",
      summary: summarizeText(text, `${record.fileName} 已在本机生成文本摘录。`),
      excerpt: text,
      warnings: text.length >= LOCAL_TEXT_EXCERPT_CHARS ? [`仅保留前 ${LOCAL_TEXT_EXCERPT_CHARS} 个字符作为本次发送候选。`] : [],
      localOnly: true,
    };
  }
  if (record.contentType === "application/pdf" || suffix === ".pdf") {
    const text = extractReadablePdfText(path, LOCAL_TEXT_EXCERPT_CHARS);
    return {
      fileId: record.id,
      fileName: record.fileName,
      kind: "pdf",
      extractionStatus: text ? "pdf_text_ready" : "pdf_text_unavailable",
      sendForm: text ? "excerpt" : "original_file",
      targetDefault: "chat_session",
      summary: text
        ? summarizeText(text, `${record.fileName} 已在本机抽取到可读 PDF 文本。`)
        : "未在本机抽取到可读 PDF 文本；确认发送后会作为会话临时原文件交给后端处理。",
      excerpt: text || null,
      warnings: text ? [] : ["可能是扫描件、图片型 PDF、加密 PDF 或压缩文本流；本地 MVP 无法稳定抽取。"],
      localOnly: true,
    };
  }
  if (record.contentType.startsWith("image/")) {
    return {
      fileId: record.id,
      fileName: record.fileName,
      kind: "image",
      extractionStatus: "image_preview_ready",
      sendForm: "original_file",
      targetDefault: "chat_session",
      summary: "图片已在本机生成预览；确认发送后会进入后端多模态模型链路。",
      excerpt: null,
      warnings: [],
      localOnly: true,
    };
  }
  return {
    fileId: record.id,
    fileName: record.fileName,
    kind: "file",
    extractionStatus: "metadata_only",
    sendForm: "original_file",
    targetDefault: "agent_temp_file",
    summary: "当前类型仅生成本机元数据；确认发送后会作为会话临时文件处理。",
    excerpt: null,
    warnings: ["该文件类型暂不支持本机文本预处理。"],
    localOnly: true,
  };
}

function isTextLike(contentType: string, suffix: string) {
  return (
    contentType.startsWith("text/") ||
    ["text/markdown", "application/json", "application/yaml"].includes(contentType) ||
    [".txt", ".md", ".markdown", ".csv", ".json", ".yaml", ".yml", ".log"].includes(suffix)
  );
}

function readTextExcerpt(path: string) {
  const text = readFileSync(path, "utf-8").replace(/\r\n/g, "\n").trim();
  return text.slice(0, LOCAL_TEXT_EXCERPT_CHARS);
}

function summarizeText(text: string, fallback: string) {
  const lines = text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 4)
    .join(" ");
  return (lines || fallback).slice(0, SUMMARY_CHARS);
}

function extractReadablePdfText(path: string, limit: number) {
  const raw = readFileSync(path).toString("latin1");
  const chunks = Array.from(raw.matchAll(/BT([\s\S]*?)ET/g)).map((match) => match[1]);
  const candidates = chunks.length ? chunks : [raw];
  const texts: string[] = [];
  for (const chunk of candidates) {
    for (const match of chunk.matchAll(/\((?:\\.|[^\\)])*\)\s*Tj/g)) {
      texts.push(decodePdfLiteral(match[0].replace(/\s*Tj$/, "")));
    }
    for (const match of chunk.matchAll(/\[(.*?)\]\s*TJ/gs)) {
      for (const literal of match[1].match(/\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]+>/g) ?? []) {
        texts.push(literal.startsWith("<") ? decodePdfHex(literal) : decodePdfLiteral(literal));
      }
    }
    for (const match of chunk.matchAll(/<([0-9A-Fa-f\s]+)>\s*Tj/g)) {
      texts.push(decodePdfHex(`<${match[1]}>`));
    }
  }
  const cleaned = texts
    .map((value) => value.replace(/\s+/g, " ").trim())
    .filter((value) => value.length > 1 && /[\p{L}\p{N}]/u.test(value))
    .join("\n")
    .trim();
  return cleaned.slice(0, limit);
}

function decodePdfLiteral(value: string) {
  const body = value.trim().replace(/^\(/, "").replace(/\)$/, "");
  return body
    .replace(/\\n/g, "\n")
    .replace(/\\r/g, "\r")
    .replace(/\\t/g, "\t")
    .replace(/\\b/g, "\b")
    .replace(/\\f/g, "\f")
    .replace(/\\([()\\])/g, "$1")
    .replace(/\\(\d{1,3})/g, (_match, octal: string) => String.fromCharCode(Number.parseInt(octal, 8)));
}

function decodePdfHex(value: string) {
  const hex = value.replace(/[<>\s]/g, "");
  if (!hex) return "";
  const bytes: number[] = [];
  for (let index = 0; index < hex.length; index += 2) {
    bytes.push(Number.parseInt(hex.slice(index, index + 2).padEnd(2, "0"), 16));
  }
  if (bytes[0] === 0xfe && bytes[1] === 0xff) {
    const chars: string[] = [];
    for (let index = 2; index + 1 < bytes.length; index += 2) {
      chars.push(String.fromCharCode((bytes[index] << 8) + bytes[index + 1]));
    }
    return chars.join("");
  }
  return Buffer.from(bytes).toString("latin1");
}
