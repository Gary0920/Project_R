import { spawn, spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const devServerHost = "127.0.0.1";
const requestedDevServerPort = process.env.PROJECT_R_FRONTEND_PORT
  ? Number(process.env.PROJECT_R_FRONTEND_PORT)
  : undefined;
const strictDevServerPort = process.env.PROJECT_R_STRICT_FRONTEND_PORT === "1"
  || process.env.PROJECT_R_STRICT_FRONTEND_PORT?.toLowerCase() === "true";

if (requestedDevServerPort !== undefined && (!Number.isInteger(requestedDevServerPort) || requestedDevServerPort <= 0)) {
  throw new Error(`PROJECT_R_FRONTEND_PORT must be a positive integer, got ${process.env.PROJECT_R_FRONTEND_PORT}`);
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function waitForDevServer(url) {
  let lastError;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.status < 500) {
        return;
      }
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(100);
  }
  throw lastError ?? new Error(`Timed out waiting for ${url}`);
}
const tscBinary = resolve(
  projectRoot,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "tsc.exe" : "tsc",
);

const tsc = spawnSync(
  tscBinary,
  ["-p", "tsconfig.main.json"],
  { cwd: projectRoot, encoding: "utf-8" },
);

if (tsc.status !== 0) {
  if (tsc.stdout) {
    process.stdout.write(tsc.stdout);
  }
  if (tsc.stderr) {
    process.stderr.write(tsc.stderr);
  }
  if (tsc.error) {
    console.error(tsc.error);
  }
  process.exit(tsc.status ?? 1);
}

const server = await createServer({
  configFile: resolve(projectRoot, "vite.config.ts"),
  root: projectRoot,
  server: {
    host: devServerHost,
    ...(requestedDevServerPort ? { port: requestedDevServerPort, strictPort: strictDevServerPort } : {}),
  },
});
await server.listen();

const addressInfo = server.httpServer?.address();
const port = typeof addressInfo === "object" && addressInfo ? addressInfo.port : undefined;
if (!port) {
  await server.close();
  throw new Error("Vite dev server did not expose a TCP port.");
}
const address = `http://${devServerHost}:${port}/`;
await waitForDevServer(address);
server.printUrls();

const electronBinary = resolve(
  projectRoot,
  "node_modules",
  "electron",
  "dist",
  process.platform === "win32" ? "electron.exe" : "electron",
);

const electron = spawn(
  electronBinary,
  [projectRoot],
  {
    cwd: projectRoot,
    stdio: "inherit",
    env: {
      ...process.env,
      NO_PROXY: [process.env.NO_PROXY, "localhost", "127.0.0.1", "::1", "<-loopback>"].filter(Boolean).join(","),
      no_proxy: [process.env.no_proxy, "localhost", "127.0.0.1", "::1", "<-loopback>"].filter(Boolean).join(","),
      VITE_DEV_SERVER_URL: address,
      PROJECT_R_PRELOAD_PATH: resolve(projectRoot, "src/preload/preload.cjs"),
    },
  },
);

electron.on("exit", async (code) => {
  await server.close();
  process.exit(code ?? 0);
});

process.on("SIGINT", async () => {
  electron.kill();
  await server.close();
  process.exit(0);
});
