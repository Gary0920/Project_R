import { strict as assert } from "node:assert";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { createPrivateWorkspaceService } from "../src/main/private-workspace";

const tempRoot = mkdtempSync(join(tmpdir(), "project-r-private-workspace-"));

try {
  const documentsDir = join(tempRoot, "Documents");
  const userDataDir = join(tempRoot, "UserData");
  const sourceDir = join(tempRoot, "SourceFiles");
  const service = createPrivateWorkspaceService({ userDataDir, documentsDir });

  const config = service.readConfig();
  assert.equal(resolve(config.rootPath), resolve(join(documentsDir, "Project_R", "私人空间")));
  assert.ok(existsSync(join(config.rootPath, "00-Inbox-快捷投放")));
  assert.ok(existsSync(service.getConfigPath()));

  mkdirSync(sourceDir, { recursive: true });
  const sourceTextPath = join(sourceDir, "sample.txt");
  const sourcePdfPath = join(sourceDir, "readable.pdf");
  const sourceImagePath = join(sourceDir, "pixel.png");
  writeFileSync(sourceTextPath, "本机文件验证\nLocal selected file verification\nLine 3", "utf-8");
  writeFileSync(
    sourcePdfPath,
    "%PDF-1.4\n1 0 obj <<>> endobj\n2 0 obj << /Length 76 >> stream\nBT /F1 12 Tf 72 720 Td (Readable PDF text from private workspace) Tj ET\nendstream endobj\n%%EOF",
    "latin1",
  );
  writeFileSync(
    sourceImagePath,
    Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=", "base64"),
  );

  const added = service.copyFilesToInbox([sourceTextPath, sourceTextPath, sourcePdfPath, sourceImagePath]);
  assert.equal(added.length, 4);
  assert.ok(added.some((item) => item.relativePath === "00-Inbox-快捷投放/sample.txt"));
  assert.ok(added.some((item) => item.relativePath === "00-Inbox-快捷投放/sample (1).txt"));
  assert.ok(added.every((item) => item.sourceLabel === "本机选择"));
  assert.ok(added.every((item) => item.lastAuthorizationStatus === "pending"));

  const manifest = service.readManifest();
  assert.equal(manifest.length, 4);
  assert.ok(existsSync(service.getManifestPath()));
  assert.ok(!JSON.stringify(manifest).includes(tempRoot));

  const payloads = service.readFilePayloads(added.map((item) => join(config.rootPath, item.relativePath)));
  assert.equal(payloads.length, 4);
  assert.ok(!JSON.stringify(payloads.map(({ base64: _base64, ...item }) => item)).includes(tempRoot));
  assert.ok(payloads.find((item) => item.fileName === "sample.txt")?.preprocess.excerpt?.includes("本机文件验证"));
  assert.equal(payloads.find((item) => item.fileName === "readable.pdf")?.preprocess.extractionStatus, "pdf_text_ready");
  assert.ok(payloads.find((item) => item.fileName === "readable.pdf")?.preprocess.excerpt?.includes("Readable PDF text"));
  assert.equal(payloads.find((item) => item.fileName === "pixel.png")?.preprocess.extractionStatus, "image_preview_ready");

  const authorized = service.setAuthorization([payloads[0].id], "authorized");
  assert.equal(authorized.find((item) => item.id === payloads[0].id)?.lastAuthorizationStatus, "authorized");
  const uploaded = service.setAuthorization([payloads[0].id], "uploaded");
  assert.equal(uploaded.find((item) => item.id === payloads[0].id)?.lastAuthorizationStatus, "uploaded");

  const customRoot = join(tempRoot, "CustomPrivateRoot");
  const customConfig = service.setRoot(customRoot);
  assert.equal(resolve(customConfig.rootPath), resolve(customRoot));
  assert.equal(customConfig.isDefault, false);
  assert.ok(existsSync(join(customRoot, "00-Inbox-快捷投放")));

  const worker = service.getWorkerStatus();
  assert.equal(worker.available, true);
  assert.equal(worker.capabilities.quickDrop, true);
  assert.equal(worker.capabilities.readablePdfText, true);
  assert.ok(worker.supportedParsingTypes.includes("readable_pdf_text"));

  const originalText = readFileSync(sourceTextPath, "utf-8");
  const projectCopy = join(tempRoot, "ProjectCopy", "99-未归档文件", "sample.txt");
  mkdirSync(join(tempRoot, "ProjectCopy", "99-未归档文件"), { recursive: true });
  writeFileSync(projectCopy, Buffer.from(payloads[0].base64, "base64"));
  assert.equal(readFileSync(projectCopy, "utf-8"), originalText);
  assert.equal(readFileSync(sourceTextPath, "utf-8"), originalText);

  console.log("private workspace verification passed");
} finally {
  rmSync(tempRoot, { recursive: true, force: true });
}
