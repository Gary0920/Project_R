import { apiRequest, type ApiClientOptions } from "./client";
import type { CurrentUserResponse } from "./types";

export function updateCurrentUser(
  options: ApiClientOptions,
  data: { nickname?: string; avatar?: string },
) {
  return apiRequest<CurrentUserResponse>(options, "/auth/me", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}
