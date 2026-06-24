export type ClientUpdateInfo = {
  id: number;
  version: string;
  platform: string;
  release_notes: string;
  minimum_supported_version: string;
  is_force_update: boolean;
  size_bytes: number;
  sha256: string;
  filename: string;
  download_url: string;
  is_active: boolean;
  created_at: string;
};

export type LatestClientUpdateResponse = {
  update_available: boolean;
  current_version: string;
  latest: ClientUpdateInfo | null;
};

export type ClientUpdateReleaseListResponse = {
  items: ClientUpdateInfo[];
};
