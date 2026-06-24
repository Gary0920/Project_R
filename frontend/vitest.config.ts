import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

const packageJson = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf-8"),
) as { version?: string };

export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.VITE_APP_VERSION": JSON.stringify(
      packageJson.version ?? "0.1.0",
    ),
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/renderer/test-setup.ts"],
    include: ["src/renderer/**/*.test.{ts,tsx}"],
    globals: true,
  },
});
