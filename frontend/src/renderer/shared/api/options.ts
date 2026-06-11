export function createApiOptions(
  baseUrl: string,
  token: string | null,
  onUnauthorized: () => void,
) {
  return { baseUrl, token, onUnauthorized };
}
