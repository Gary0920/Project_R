import { apiRequest, type ApiClientOptions } from "../../shared/api/client";
import type { ClientUpdateInfo, ClientUpdateReleaseListResponse, LatestClientUpdateResponse } from "../../shared/api/types";

export function getLatestClientUpdate(options: ApiClientOptions, currentVersion: string, platform: string) {
  const query = new URLSearchParams({
    current_version: currentVersion,
    platform,
  });
  return apiRequest<LatestClientUpdateResponse>(options, `/updates/latest?${query.toString()}`);
}

export function listClientUpdateReleases(options: ApiClientOptions, platform = "win32") {
  const query = new URLSearchParams({ platform });
  return apiRequest<ClientUpdateReleaseListResponse>(options, `/updates/admin/releases?${query.toString()}`);
}

export type UploadClientUpdateReleaseInput = {
  version: string;
  releaseNotes: string;
  minimumSupportedVersion: string;
  platform: string;
  isForceUpdate: boolean;
  isActive: boolean;
  file: File;
};

export function uploadClientUpdateRelease(options: ApiClientOptions, input: UploadClientUpdateReleaseInput) {
  const form = new FormData();
  form.append("version", input.version);
  form.append("release_notes", input.releaseNotes);
  form.append("minimum_supported_version", input.minimumSupportedVersion);
  form.append("platform", input.platform);
  form.append("is_force_update", String(input.isForceUpdate));
  form.append("is_active", String(input.isActive));
  form.append("file", input.file);
  return apiRequest<ClientUpdateInfo>(options, "/updates/admin/releases", {
    method: "POST",
    body: form,
  });
}
