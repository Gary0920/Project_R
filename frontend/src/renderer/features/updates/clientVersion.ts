export const FALLBACK_CLIENT_VERSION = import.meta.env.VITE_APP_VERSION || "0.1.0";
export const UPDATE_DOWNLOAD_DRY_RUN = import.meta.env.DEV || import.meta.env.VITE_UPDATE_DRY_RUN === "1";

function clientVersionKey(version: string) {
  const cleaned = version.trim().replace(/^[vV]/, "");
  const values = cleaned.split(/[.\-_+]/).map((part) => {
    const match = part.match(/^(\d+)/);
    return match ? Number(match[1]) : -1;
  });
  while (values.length < 4) values.push(0);
  return values.slice(0, 4);
}

export function compareClientVersions(left: string, right: string) {
  const leftKey = clientVersionKey(left);
  const rightKey = clientVersionKey(right);
  for (let index = 0; index < Math.max(leftKey.length, rightKey.length); index += 1) {
    const leftValue = leftKey[index] ?? 0;
    const rightValue = rightKey[index] ?? 0;
    if (leftValue !== rightValue) return leftValue > rightValue ? 1 : -1;
  }
  return 0;
}

export async function resolveCurrentClientVersion() {
  try {
    const version = await window.projectR?.updates?.getCurrentVersion?.();
    const normalized = version?.trim();
    if (normalized) return normalized;
  } catch {
    // Browser/dev renderer falls back to the build-time package version.
  }
  return FALLBACK_CLIENT_VERSION;
}

export function formatUpdateBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatUpdateSpeed(bytesPerSecond: number) {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return "";
  return `${formatUpdateBytes(bytesPerSecond)}/s`;
}
