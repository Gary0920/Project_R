import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * Admin credentials — MUST come from environment variables.
 * Set PW_ADMIN_USER and PW_ADMIN_PASS before running.
 * Tests skip with a clear message if either is missing.
 */
const ADMIN_USER = process.env.PW_ADMIN_USER ?? "";
const ADMIN_PASS = process.env.PW_ADMIN_PASS ?? "";

const SKIP_REASON =
  "Set PW_ADMIN_USER and PW_ADMIN_PASS environment variables to run this suite";

const MEETING_TOOLBAR_BUTTONS = [
  "上传/转写录音",
  "保存转录文本",
  "说话人映射",
  "术语纠错",
  "生成纪要与行动项",
  "重跑纪要",
  "录入此会议",
  "录入行动项",
  "重试转录",
  "重试纪要生成",
];

async function login(page: Page, user: string, pass: string) {
  await page.goto("/#/login");
  await page.waitForLoadState("networkidle");

  const enterLoginBtn = page.locator("button", { hasText: "进入登录" });
  if (await enterLoginBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await enterLoginBtn.click();
    await page.waitForTimeout(2000);
  }

  await page.locator("#username").fill(user);
  await page.locator("#password").fill(pass);
  await page.locator("button.alp-btn-login").click();
  await page.waitForURL("**/app**", { timeout: 15000 });
}

async function switchToTestWorkspace(page: Page) {
  const wsToggle = page.locator("button.workspace-section-main, button.workspace-section-chevron-btn").first();
  await wsToggle.waitFor({ state: "visible", timeout: 5000 });
  await wsToggle.click();
  await page.waitForTimeout(1500);

  const testName = page.locator(".workspace-list-item .workspace-list-name", { hasText: "TEST" });
  await testName.waitFor({ state: "visible", timeout: 5000 });
  await testName.click();
  await page.waitForTimeout(3000);

  await expect(
    page.locator("button.workspace-section-main[title*='TEST'], button.workspace-section-main:has-text('TEST')")
  ).toBeVisible({ timeout: 5000 });

  const drawerCloseBtn = page
    .locator(".workspace-member-drawer-header button, .workspace-member-drawer [aria-label*='关闭']")
    .first();
  if (await drawerCloseBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await drawerCloseBtn.click();
    await page.waitForTimeout(800);
  }
  await page.mouse.click(300, 100);
  await page.waitForTimeout(500);
}

async function openFilePanel(page: Page) {
  const fileMgrBtn = page.locator("button[title='文件管理'], button[title='关闭文件管理']");
  await fileMgrBtn.waitFor({ state: "visible", timeout: 10000 });
  await fileMgrBtn.click();
  await page.waitForTimeout(1500);
  await expect(page.locator(".workspace-file-panel-layout, .agent-file-panel").first()).toBeVisible({ timeout: 5000 });
}

async function navigateToMeetingRoot(page: Page) {
  const meetingDir = page.locator("text=20-会议与沟通");
  await meetingDir.waitFor({ state: "visible", timeout: 8000 });
  await meetingDir.click();
  await page.waitForTimeout(1500);
}

// ─── Hook: skip entire describe block if credentials missing ──────────────

test.describe("Meeting Workflow UI", () => {
  const hasCreds = Boolean(ADMIN_USER && ADMIN_PASS);

  test("all toolbar buttons are present in 20-会议与沟通", async ({ page }) => {
    test.skip(!hasCreds, SKIP_REASON);
    await login(page, ADMIN_USER, ADMIN_PASS);
    await switchToTestWorkspace(page);
    await openFilePanel(page);
    await navigateToMeetingRoot(page);

    const toolbar = page.locator("[data-testid='meeting-toolbar'], .workspace-meeting-toolbar");
    await expect(toolbar).toBeVisible();

    for (const label of MEETING_TOOLBAR_BUTTONS) {
      const btn = toolbar.locator("button", { hasText: label });
      await expect(btn).toBeVisible({ timeout: 3000 });
    }
  });

  // ── Download validation via API intercept ──

  test("right-click download triggers correct file content API", async ({ page }) => {
    test.skip(!hasCreds, SKIP_REASON);
    await login(page, ADMIN_USER, ADMIN_PASS);
    await switchToTestWorkspace(page);
    await openFilePanel(page);
    await navigateToMeetingRoot(page);

    const firstSubdir = page.locator(".workspace-file-row.is-directory").first();
    if (await firstSubdir.isVisible({ timeout: 3000 }).catch(() => false)) {
      await firstSubdir.click();
      await page.waitForTimeout(1000);
    }

    const fileRow = page.locator(".workspace-file-row:not(.is-directory)").first();
    await expect(fileRow).toBeVisible({ timeout: 5000 });
    const filePath = await fileRow.getAttribute("title") ?? "";
    expect(filePath.length).toBeGreaterThan(0);

    // Intercept the file content API — clear before each trigger
    let calls: string[] = [];
    await page.route("**/workspaces/**/files/content?path=**", async (route: Route) => {
      calls.push(route.request().url());
      await route.fulfill({ status: 200, body: "mock" });
    });

    // Right-click the file → click "下载" in context menu
    await fileRow.click({ button: "right" });
    await page.waitForTimeout(500);
    const contextMenu = page.locator(".workspace-file-context-menu");
    await expect(contextMenu).toBeVisible({ timeout: 2000 });
    const downloadItem = contextMenu.locator("button", { hasText: "下载" });
    await expect(downloadItem).toBeVisible();
    await downloadItem.click();
    await page.waitForTimeout(1000);

    // Assert the content API was called with the correct file path
    expect(calls.length).toBeGreaterThanOrEqual(1);
    const lastCall = calls[calls.length - 1];
    expect(lastCall).toContain("path=" + encodeURIComponent(filePath));
    calls = []; // reset for next test

    // Now open preview and test the preview download button
    await fileRow.click();
    await page.waitForTimeout(1500);

    // Preview loading already called files/content; clear so only the
    // download-button click is counted below
    calls = [];

    const previewDlBtn = page.locator(
      ".workspace-file-preview-actions button[aria-label*='下载'], .workspace-file-preview-actions button[title*='下载文件']"
    );
    await expect(previewDlBtn).toBeVisible({ timeout: 3000 });
    await previewDlBtn.click();
    await page.waitForTimeout(1000);

    // Assert a new API call happened for the preview download
    expect(calls.length).toBeGreaterThanOrEqual(1);
    const previewCall = calls[calls.length - 1];
    expect(previewCall).toContain("path=" + encodeURIComponent(filePath));

    // Cleanup
    await page.unroute("**/workspaces/**/files/content?path=**");
    const closeBtn = page.locator("button[aria-label*='关闭预览']").first();
    if (await closeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await closeBtn.click();
      await page.waitForTimeout(500);
    }
  });

  // ── Media preflight with filechooser + mocked API ──

  test("preflight confirmation shows estimated duration and cost for long media", async ({ page }) => {
    test.skip(!hasCreds, SKIP_REASON);
    await login(page, ADMIN_USER, ADMIN_PASS);
    await switchToTestWorkspace(page);
    await openFilePanel(page);
    await navigateToMeetingRoot(page);

    // Mock the preflight API to return long-media values
    const PREFLIGHT_URL = "**/workspaces/**/meetings/transcribe/media/preflight";
    await page.route(PREFLIGHT_URL, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          filename: "test-recording.mp3",
          size_mb: 68.5,
          estimated_duration_minutes: 35,
          is_long_media: true,
          estimated_segments: 7,
          estimated_cost_note: "预估 35 分钟，将使用 MiMo V2.5 模型转录。长视频将自动分段处理。",
          warnings: ["媒体时长超过 30 分钟（预估 35 分钟），将自动分段转录（7 段）"],
          model: "MiMo V2.5",
        }),
      });
    });

    // Set up filechooser listener before clicking the button
    const fileChooserPromise = page.waitForEvent("filechooser", { timeout: 5000 });

    // Click "上传/转写录音" to trigger file input
    const transcribeBtn = page.locator("button", { hasText: "上传/转写录音" });
    await expect(transcribeBtn).toBeVisible();
    await transcribeBtn.click();

    // Respond to the file chooser with a dummy media file
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles({
      name: "test-recording.mp3",
      mimeType: "audio/mpeg",
      buffer: Buffer.alloc(1024),
    });
    await page.waitForTimeout(1000);

    // Assert the confirmation dialog appears with cost details
    const confirmCard = page.locator(".workspace-confirm-card");
    await expect(confirmCard).toBeVisible({ timeout: 5000 });

    // Assert file name present
    await expect(confirmCard).toContainText("test-recording.mp3");

    // Assert estimated duration
    await expect(confirmCard).toContainText("35");

    // Assert segment count
    await expect(confirmCard).toContainText("7");

    // Assert long-media / cost warning
    await expect(confirmCard).toContainText("高成本");
    await expect(confirmCard).toContainText("分段数");
    await expect(confirmCard).toContainText("MiMo V2.5");

    // Assert both buttons exist
    const cancelBtn = confirmCard.locator("button", { hasText: "取消" });
    const confirmBtn = confirmCard.locator("button", { hasText: "确认转录" });
    await expect(cancelBtn).toBeVisible();
    await expect(confirmBtn).toBeVisible();

    // Cancel — do NOT confirm upload/transcription
    await cancelBtn.click();
    await page.waitForTimeout(500);

    // Verify dialog closed
    await expect(confirmCard).not.toBeVisible({ timeout: 3000 });
  });
});
