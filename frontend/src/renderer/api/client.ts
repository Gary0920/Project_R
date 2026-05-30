import type { ApiErrorPayload } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type ApiClientOptions = {
  baseUrl: string;
  token?: string | null;
  onUnauthorized?: () => void;
};

export async function apiRequest<T>(
  options: ApiClientOptions,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  const response = await fetch(`${options.baseUrl}${path}`, {
    ...init,
    headers: {
      ...(isFormData ? {} : { "content-type": "application/json" }),
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      ...init.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      options.onUnauthorized?.();
    }
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      detail = payload.detail || detail;
    } catch {
      // Keep the status text when the server returns no JSON body.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}
