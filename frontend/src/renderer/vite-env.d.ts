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
  status: "downloading" | "verifying" | "ready" | "error";
  receivedBytes: number;
  totalBytes: number;
  percent: number;
  bytesPerSecond: number;
  filePath?: string;
  message?: string;
  dryRun?: boolean;
};
