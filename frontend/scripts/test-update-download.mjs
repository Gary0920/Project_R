import { strict as assert } from "node:assert";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { downloadUpdatePackageToFile } from "../src/main/update-download.ts";

const payload = Buffer.from("Project_R fake update package for dry-run verification.\n", "utf-8");
const sha256 = createHash("sha256").update(payload).digest("hex");
const tempDir = mkdtempSync(join(tmpdir(), "project-r-update-"));

const server = createServer((request, response) => {
  if (request.url === "/Project_R-0.2.0.exe") {
    response.writeHead(200, {
      "content-length": payload.length,
      "content-type": "application/octet-stream",
    });
    response.end(payload);
    return;
  }
  response.writeHead(404);
  response.end();
});

try {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;

  const progress = [];
  const result = await downloadUpdatePackageToFile(
    {
      baseUrl,
      version: "0.2.0",
      filename: "Project_R-0.2.0.exe",
      downloadUrl: "/Project_R-0.2.0.exe",
      sha256,
      sizeBytes: payload.length,
      dryRun: true,
      downloadsDir: tempDir,
    },
    (item) => progress.push(item),
  );

  assert.equal(result.ok, true);
  assert.equal(result.dryRun, true);
  assert(result.filePath);
  assert.deepEqual(readFileSync(result.filePath), payload);
  assert(progress.some((item) => item.status === "downloading"));
  assert(progress.some((item) => item.status === "verifying"));
  assert(progress.some((item) => item.status === "ready" && item.percent === 100));

  await assert.rejects(
    () => downloadUpdatePackageToFile(
      {
        baseUrl,
        version: "0.2.1",
        filename: "Project_R-0.2.1.exe",
        downloadUrl: "/Project_R-0.2.0.exe",
        sha256: "0".repeat(64),
        sizeBytes: payload.length,
        dryRun: true,
        downloadsDir: tempDir,
      },
      () => {},
    ),
    /校验失败/,
  );
  assert.equal(existsSync(join(tempDir, "Project_R-0.2.1.exe")), false);
  console.log("update download dry-run smoke test passed");
} finally {
  await new Promise((resolve) => server.close(resolve));
  rmSync(tempDir, { recursive: true, force: true });
}
