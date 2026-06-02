/// <reference types="vite/client" />

interface Window {
  projectR?: {
    platform: string;
    window?: {
      minimize: () => Promise<void>;
      toggleMaximize: () => Promise<boolean>;
      close: () => Promise<void>;
      isMaximized: () => Promise<boolean>;
      onStateChange: (callback: (state: { isMaximized: boolean }) => void) => () => void;
    };
    prompts?: {
      listUser: () => Promise<UserPromptRecord[]>;
      saveUser: (input: { id?: string; name: string; content: string }) => Promise<UserPromptRecord>;
      deleteUser: (id: string) => Promise<UserPromptRecord[]>;
    };
    privateWorkspace?: {
      getConfig: () => Promise<PrivateWorkspaceConfig>;
      getWorkerStatus: () => Promise<PrivateWorkspaceWorkerStatus>;
      chooseRoot: () => Promise<PrivateWorkspaceConfig>;
      openRoot: () => Promise<PrivateWorkspaceConfig>;
      resetRoot: () => Promise<PrivateWorkspaceConfig>;
      getManifest: () => Promise<PrivateWorkspaceFileRecord[]>;
      quickDrop: () => Promise<{ records: PrivateWorkspaceFileRecord[]; added: PrivateWorkspaceFileRecord[] }>;
      chooseFiles: () => Promise<PrivateWorkspaceFilePayload[]>;
      setAuthorization: (input: { ids: string[]; status: "pending" | "authorized" | "uploaded" }) => Promise<PrivateWorkspaceFileRecord[]>;
    };
    updates?: {
      getCurrentVersion: () => Promise<string>;
      download: (input: UpdateDownloadInput) => Promise<UpdateDownloadResult>;
      install: (input: UpdateInstallInput) => Promise<UpdateDownloadResult>;
      onProgress: (callback: (progress: UpdateDownloadProgress) => void) => () => void;
    };
  };
}

type UserPromptRecord = {
  id: string;
  name: string;
  content: string;
  createdAt: string;
  updatedAt: string;
};

type PrivateWorkspaceConfig = {
  rootPath: string;
  isDefault: boolean;
  updatedAt: string;
};

type PrivateWorkspaceFileRecord = {
  id: string;
  relativePath: string;
  fileName: string;
  contentType: string;
  size: number;
  sha256: string;
  updatedAt: string;
  sourceLabel: string;
  lastAuthorizationStatus: "pending" | "authorized" | "uploaded";
  createdAt: string;
};

type PrivateWorkspaceFilePayload = PrivateWorkspaceFileRecord & {
  base64: string;
  preprocess: PrivateWorkspacePreprocessResult;
};

type PrivateWorkspacePreprocessResult = {
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

type PrivateWorkspaceWorkerStatus = {
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

type UpdateDownloadInput = {
  baseUrl: string;
  token?: string | null;
  version: string;
  filename: string;
  downloadUrl: string;
  sha256: string;
  sizeBytes?: number;
  dryRun?: boolean;
};

type UpdateInstallInput = {
  filePath: string;
  version?: string;
  dryRun?: boolean;
};

type UpdateDownloadResult = {
  ok: boolean;
  filePath?: string;
  dryRun?: boolean;
  message?: string;
};

type UpdateDownloadProgress = {
  version: string;
  status: "downloading" | "verifying" | "ready" | "installing" | "error";
  receivedBytes: number;
  totalBytes: number;
  percent: number;
  bytesPerSecond: number;
  filePath?: string;
  message?: string;
  dryRun?: boolean;
};
