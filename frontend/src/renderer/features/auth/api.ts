import { apiRequest, type ApiClientOptions } from "../../shared/api/client";
import type { CurrentUserResponse } from "../../shared/api/types";

export function updateCurrentUser(
  options: ApiClientOptions,
  data: { nickname?: string; avatar?: string },
) {
  return apiRequest<CurrentUserResponse>(options, "/auth/me", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function uploadCurrentUserAvatar(options: ApiClientOptions, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiRequest<CurrentUserResponse>(options, "/auth/me/avatar", {
    method: "POST",
    body: form,
  });
}
