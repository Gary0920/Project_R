export const APP_NAME = "Project_R";

export const DEFAULT_API_BASE_URL = import.meta.env.VITE_DEFAULT_API_BASE_URL;

if (!DEFAULT_API_BASE_URL) {
  throw new Error("VITE_DEFAULT_API_BASE_URL is required.");
}
