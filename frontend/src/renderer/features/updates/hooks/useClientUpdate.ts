import { useCallback, useEffect, useRef, useState } from "react";

import { getLatestClientUpdate } from "../api";
import {
  FALLBACK_CLIENT_VERSION,
  UPDATE_DOWNLOAD_DRY_RUN,
  compareClientVersions,
  resolveCurrentClientVersion,
} from "../clientVersion";
import type { ClientUpdateInfo } from "../../../shared/api/types";

type ClientUpdateStep = "available" | "downloading" | "installing" | "ready" | "failed";

type UseClientUpdateOptions = {
  serverUrl: string;
  token: string | null;
};

export function useClientUpdate({ serverUrl, token }: UseClientUpdateOptions) {
  const [clientVersion, setClientVersion] = useState(FALLBACK_CLIENT_VERSION);
  const [availableUpdate, setAvailableUpdate] = useState<ClientUpdateInfo | null>(null);
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);
  const [updateStep, setUpdateStep] = useState<ClientUpdateStep>("available");
  const [updateProgress, setUpdateProgress] = useState<UpdateDownloadProgress | null>(null);
  const [downloadedUpdatePath, setDownloadedUpdatePath] = useState("");
  const [updateError, setUpdateError] = useState("");
  const updateCheckStartedRef = useRef(false);

  const checkForClientUpdate = useCallback(async () => {
    try {
      const currentVersion = await resolveCurrentClientVersion();
      const platform = window.projectR?.platform ?? "win32";
      setClientVersion(currentVersion);
      const response = await getLatestClientUpdate(
        { baseUrl: serverUrl, token: null, onUnauthorized: undefined },
        currentVersion,
        platform,
      );
      if (response.latest && compareClientVersions(currentVersion, response.latest.version) >= 0) {
        setAvailableUpdate(null);
        setUpdateDialogOpen(false);
        setUpdateStep("available");
        setUpdateProgress(null);
        setDownloadedUpdatePath("");
        setUpdateError("");
        return;
      }
      if (response.update_available && response.latest) {
        setAvailableUpdate(response.latest);
        setUpdateStep("available");
        setUpdateProgress(null);
        setDownloadedUpdatePath("");
        setUpdateError("");
        setUpdateDialogOpen(true);
      }
    } catch {
      // Update checks are opportunistic and must not block login or chat usage.
    }
  }, [serverUrl]);

  const startClientUpdateDownload = useCallback(async () => {
    if (!availableUpdate) return;
    if (!window.projectR?.updates?.download || !window.projectR?.updates?.install) {
      setUpdateStep("failed");
      setUpdateError("自动更新失败，请联系管理员获取最新版安装包。");
      return;
    }
    setUpdateStep("downloading");
    setUpdateError("");
    setDownloadedUpdatePath("");
    setUpdateProgress({
      version: availableUpdate.version,
      status: "downloading",
      receivedBytes: 0,
      totalBytes: availableUpdate.size_bytes,
      percent: 0,
      bytesPerSecond: 0,
      dryRun: UPDATE_DOWNLOAD_DRY_RUN,
    });
    const result = await window.projectR.updates.download({
      baseUrl: serverUrl,
      token,
      version: availableUpdate.version,
      filename: availableUpdate.filename,
      downloadUrl: availableUpdate.download_url,
      sha256: availableUpdate.sha256,
      sizeBytes: availableUpdate.size_bytes,
      dryRun: UPDATE_DOWNLOAD_DRY_RUN,
    });
    if (!result.ok || !result.filePath) {
      setUpdateStep("failed");
      setUpdateError("自动更新失败，请联系管理员获取最新版安装包。");
      return;
    }
    setDownloadedUpdatePath(result.filePath);
    setUpdateStep("installing");
    setUpdateProgress({
      version: availableUpdate.version,
      status: "installing",
      receivedBytes: availableUpdate.size_bytes,
      totalBytes: availableUpdate.size_bytes,
      percent: 100,
      bytesPerSecond: 0,
      filePath: result.filePath,
      message: "正在静默安装更新，完成后会自动重启应用...",
      dryRun: UPDATE_DOWNLOAD_DRY_RUN,
    });
    const installResult = await window.projectR.updates.install({
      filePath: result.filePath,
      version: availableUpdate.version,
      dryRun: UPDATE_DOWNLOAD_DRY_RUN,
    });
    if (!installResult.ok) {
      setUpdateStep("failed");
      setUpdateError("自动更新失败，请联系管理员获取最新版安装包。");
      return;
    }
    if (installResult.dryRun) {
      setUpdateDialogOpen(false);
    }
  }, [availableUpdate, serverUrl, token]);

  useEffect(() => {
    if (!window.projectR?.updates?.onProgress) return;
    return window.projectR.updates.onProgress((progress) => {
      setUpdateProgress(progress);
      if (progress.status === "downloading" || progress.status === "verifying") {
        setUpdateStep("downloading");
      }
      if (progress.status === "installing") {
        setUpdateStep("installing");
      }
      if (progress.status === "ready") {
        setDownloadedUpdatePath(progress.filePath ?? "");
        setUpdateStep("downloading");
      }
      if (progress.status === "error") {
        setUpdateStep("failed");
        setUpdateError("自动更新失败，请联系管理员获取最新版安装包。");
      }
    });
  }, []);

  useEffect(() => {
    if (!token || updateCheckStartedRef.current) return;
    updateCheckStartedRef.current = true;
    void checkForClientUpdate();
  }, [checkForClientUpdate, token]);

  return {
    availableUpdate,
    clientVersion,
    downloadedUpdatePath,
    setUpdateDialogOpen,
    setUpdateStep,
    startClientUpdateDownload,
    updateDialogOpen,
    updateError,
    updateProgress,
    updateStep,
  };
}
