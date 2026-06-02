import { createHash } from "node:crypto";
import { createWriteStream, existsSync, mkdirSync, unlinkSync } from "node:fs";
import { basename, join } from "node:path";

export type UpdateDownloadInput = {
  baseUrl: string;
  token?: string | null;
  version: string;
  filename: string;
  downloadUrl: string;
  sha256: string;
  sizeBytes?: number;
  dryRun?: boolean;
  downloadsDir: string;
};

export type UpdateProgress = {
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

function safeUpdateFilename(filename: string, version: string) {
  const rawName = basename(filename || `Project_R-${version}.exe`);
  const safe = rawName.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  return safe || `Project_R-${version}.exe`;
}

async function writeChunk(output: NodeJS.WritableStream, chunk: Uint8Array) {
  await new Promise<void>((resolve, reject) => {
    output.write(Buffer.from(chunk), (error?: Error | null) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

async function closeStream(output: NodeJS.WritableStream) {
  await new Promise<void>((resolve, reject) => {
    output.end((error?: Error | null) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

export async function downloadUpdatePackageToFile(
  input: UpdateDownloadInput,
  emitProgress: (progress: UpdateProgress) => void,
) {
  const baseUrl = input.baseUrl?.trim();
  if (!baseUrl || !input.downloadUrl || !input.version || !input.sha256 || !input.downloadsDir) {
    throw new Error("更新信息不完整");
  }
  const requestUrl = new URL(input.downloadUrl, baseUrl);
  const headers: Record<string, string> = {};
  if (input.token) {
    headers.Authorization = `Bearer ${input.token}`;
  }

  const response = await fetch(requestUrl, { headers });
  if (!response.ok || !response.body) {
    throw new Error("更新包下载失败");
  }

  mkdirSync(input.downloadsDir, { recursive: true });
  const filename = safeUpdateFilename(input.filename, input.version);
  const targetPath = join(input.downloadsDir, filename);
  const totalBytes = Number(response.headers.get("content-length") || input.sizeBytes || 0);
  const hasher = createHash("sha256");
  const output = createWriteStream(targetPath);
  const reader = response.body.getReader();
  const startedAt = Date.now();
  let receivedBytes = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      receivedBytes += value.byteLength;
      hasher.update(value);
      await writeChunk(output, value);
      const elapsedSeconds = Math.max(0.2, (Date.now() - startedAt) / 1000);
      emitProgress({
        version: input.version,
        status: "downloading",
        receivedBytes,
        totalBytes,
        percent: totalBytes > 0 ? Math.min(99, Math.round((receivedBytes / totalBytes) * 100)) : 0,
        bytesPerSecond: Math.round(receivedBytes / elapsedSeconds),
        dryRun: Boolean(input.dryRun),
      });
    }
    await closeStream(output);
  } catch (error) {
    output.destroy();
    if (existsSync(targetPath)) {
      unlinkSync(targetPath);
    }
    throw error;
  }

  emitProgress({
    version: input.version,
    status: "verifying",
    receivedBytes,
    totalBytes,
    percent: 99,
    bytesPerSecond: 0,
    dryRun: Boolean(input.dryRun),
  });

  if (input.sizeBytes && receivedBytes !== input.sizeBytes) {
    unlinkSync(targetPath);
    throw new Error("更新包大小不一致");
  }
  const actualSha256 = hasher.digest("hex");
  if (actualSha256.toLowerCase() !== input.sha256.toLowerCase()) {
    unlinkSync(targetPath);
    throw new Error("更新包校验失败");
  }

  emitProgress({
    version: input.version,
    status: "ready",
    receivedBytes,
    totalBytes: totalBytes || receivedBytes,
    percent: 100,
    bytesPerSecond: 0,
    filePath: targetPath,
    dryRun: Boolean(input.dryRun),
  });
  return { ok: true, filePath: targetPath, dryRun: Boolean(input.dryRun) };
}
