import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

const packageJson = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf-8")) as {
  version?: string;
};

export default defineConfig({
  plugins: [react()],
  base: "./",
  root: ".",
  define: {
    "import.meta.env.VITE_APP_VERSION": JSON.stringify(packageJson.version ?? "0.1.0"),
  },
  build: {
    outDir: "dist/renderer",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/@lezer")) {
            return "lezer";
          }
          if (id.includes("node_modules/@codemirror")) {
            return "codemirror";
          }
          if (
            id.includes("node_modules/crelt")
            || id.includes("node_modules/style-mod")
            || id.includes("node_modules/w3c-keyname")
          ) return "codemirror-support";
          if (id.includes("node_modules")) return "vendor";
          return undefined;
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: false,
  },
});
