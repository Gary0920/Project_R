import { describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "./client";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    status: 200,
    ...init,
  });
}

describe("apiRequest", () => {
  it("sends JSON content type and bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiRequest<{ ok: boolean }>(
      { baseUrl: "http://api.test", token: "token-1" },
      "/health",
      { method: "POST", body: JSON.stringify({ ping: true }) },
    );

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/health",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer token-1",
          "content-type": "application/json",
        }),
      }),
    );
  });

  it("calls onUnauthorized and throws ApiError for 401 responses", async () => {
    const onUnauthorized = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "认证失效" }, { status: 401, statusText: "Unauthorized" })),
    );

    await expect(
      apiRequest({ baseUrl: "http://api.test", token: "expired", onUnauthorized }, "/me"),
    ).rejects.toMatchObject({ name: "ApiError", message: "认证失效", status: 401 });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("falls back to status text when error body is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not-json", { status: 503, statusText: "Service Unavailable" })),
    );

    await expect(apiRequest({ baseUrl: "http://api.test" }, "/down")).rejects.toMatchObject({
      name: "ApiError",
      message: "Service Unavailable",
      status: 503,
    });
  });
});
