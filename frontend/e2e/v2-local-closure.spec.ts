import { expect, test, type Page, type Route } from "@playwright/test";

const BACKEND_URL = process.env.PW_BACKEND_URL ?? "http://127.0.0.1:8000";
const MOCK_TOKEN = "pw-v2-local-closure-token";
const now = () => new Date().toISOString();

const adminUser = {
  user_id: 1,
  username: "admin",
  role: "admin",
  nickname: "管理员",
  avatar: "",
  work_group: "system",
  last_login_at: now(),
};

const personalWorkspace = {
  id: 1,
  name: "个人工作台",
  slug: "personal",
  description: "个人本轮工作台",
  created_by: 1,
  member_count: 1,
  brand: "PROJECT_R",
  workspace_kind: "user",
  is_default: true,
  is_archived: false,
  is_hidden: false,
  can_rename: false,
  can_delete: false,
  created_at: now(),
  updated_at: now(),
};

const projectWorkspace = {
  id: 2,
  name: "TEST",
  slug: "TEST",
  description: "V2.1 local closure fixture",
  created_by: 1,
  member_count: 1,
  brand: "TEST",
  workspace_kind: "project",
  is_default: false,
  is_archived: false,
  is_hidden: false,
  can_rename: true,
  can_delete: false,
  created_at: now(),
  updated_at: now(),
};

type MockMessage = {
  id: number;
  session_id: number;
  role: "user" | "assistant";
  content: string;
  provider: string | null;
  model: string | null;
  token_input: number | null;
  token_output: number | null;
  token_total: number | null;
  status: string;
  error_message: string | null;
  rag_used: boolean;
  is_excluded: boolean;
  version_group_id: string | null;
  version_index: number;
  version_count: number;
  active_version: boolean;
  versions: unknown[];
  feedback_rating: number | null;
  feedback_comment: string | null;
  sources: unknown[];
  attachments: unknown[];
  generated_file?: unknown | null;
  skill_run?: unknown | null;
  agent_run: unknown | null;
  context_trace: unknown | null;
  created_at: string;
};

function message(overrides: Partial<MockMessage>): MockMessage {
  return {
    id: overrides.id ?? 1,
    session_id: overrides.session_id ?? 101,
    role: overrides.role ?? "assistant",
    content: overrides.content ?? "",
    provider: overrides.provider ?? "mock",
    model: overrides.model ?? "mock-model",
    token_input: overrides.token_input ?? 10,
    token_output: overrides.token_output ?? 20,
    token_total: overrides.token_total ?? 30,
    status: overrides.status ?? "success",
    error_message: overrides.error_message ?? null,
    rag_used: overrides.rag_used ?? false,
    is_excluded: overrides.is_excluded ?? false,
    version_group_id: overrides.version_group_id ?? null,
    version_index: overrides.version_index ?? 1,
    version_count: overrides.version_count ?? 1,
    active_version: overrides.active_version ?? true,
    versions: overrides.versions ?? [],
    feedback_rating: overrides.feedback_rating ?? null,
    feedback_comment: overrides.feedback_comment ?? null,
    sources: overrides.sources ?? [],
    attachments: overrides.attachments ?? [],
    generated_file: overrides.generated_file ?? null,
    skill_run: overrides.skill_run ?? null,
    agent_run: overrides.agent_run ?? null,
    context_trace: overrides.context_trace ?? null,
    created_at: overrides.created_at ?? now(),
  };
}

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function installMockBackend(page: Page) {
  const messages: MockMessage[] = [];
  let sessionPreview = "";

  await page.route(`${BACKEND_URL.replace(/\/$/, "")}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/auth/login" && method === "POST") {
      await fulfillJson(route, { token: MOCK_TOKEN, ...adminUser });
      return;
    }
    if (path === "/auth/me") {
      await fulfillJson(route, adminUser);
      return;
    }
    if (path === "/health") {
      await fulfillJson(route, { status: "ok" });
      return;
    }
    if (path === "/workspaces" && method === "GET") {
      await fulfillJson(route, [personalWorkspace, projectWorkspace]);
      return;
    }
    if (path === "/health/llm") {
      await fulfillJson(route, { providers: [] });
      return;
    }
    if (path === "/prompts/company") {
      await fulfillJson(route, []);
      return;
    }
    if (path === "/skills") {
      await fulfillJson(route, []);
      return;
    }
    if (path === "/notifications/counts") {
      await fulfillJson(route, { unread_count: 0, pending_count: 0 });
      return;
    }
    if (path === "/updates/latest") {
      await fulfillJson(route, { update_available: false, latest: null });
      return;
    }
    if (path === "/chat/sessions" && method === "GET") {
      await fulfillJson(route, [
        {
          id: 101,
          title: "V2.1 收口验证",
          workspace_id: 1,
          is_archived: false,
          is_pinned: false,
          created_at: now(),
          updated_at: now(),
          last_message_preview: sessionPreview,
        },
      ]);
      return;
    }
    if (path === "/chat/sessions" && method === "POST") {
      await fulfillJson(route, {
        id: 101,
        title: "V2.1 收口验证",
        workspace_id: 1,
        is_archived: false,
        is_pinned: false,
        created_at: now(),
        updated_at: now(),
        last_message_preview: sessionPreview,
      });
      return;
    }
    if (path === "/chat/sessions/101/messages" && method === "GET") {
      await fulfillJson(route, { items: messages, total: messages.length, limit: 100, offset: 0 });
      return;
    }
    if (path === "/chat/sessions/101/messages" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { content?: string };
      const user = message({
        id: 1000 + messages.length,
        role: "user",
        content: body.content ?? "",
        provider: null,
        model: null,
        token_input: null,
        token_output: null,
        token_total: null,
      });

      const source = {
        file: "gbrain:company-wiki/rules/v2-local-closure",
        source_title: "V2.1 本地收口说明",
        section_path: "知识库查询范围",
        content: "",
        score: 0.94,
        source_id: "company-wiki",
        page_slug: "rules/v2-local-closure",
        evidence_excerpt: "本轮仅展示回答实际引用片段，不枚举完整知识库 source。",
        original_source_file: "v2-local-closure.md",
        locator_label: "company-wiki / rules/v2-local-closure",
        metadata_only: false,
      };

      const isFileCommand = !(body.content ?? "").startsWith("/query");
      const assistant = message({
        id: user.id + 1,
        role: "assistant",
        content: isFileCommand ? "已生成 V2.1 收口表格。" : "这是来自 company-wiki 的只读验证回答。",
        rag_used: !isFileCommand,
        sources: isFileCommand ? [] : [source],
        generated_file: isFileCommand
          ? {
              id: "generated-v2-xlsx",
              filename: "v2-local-closure.docx",
              mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              download_url: "/documents/generated/generated-v2-xlsx/download",
            }
          : null,
        context_trace: isFileCommand
          ? { intent: "document_generation", generated_file: { id: "generated-v2-xlsx" } }
          : {
              intent: "rag_query",
              gbrain_source_id: "company-wiki",
              gbrain_status: "ok",
              gbrain_think: {
                source_id: "company-wiki",
                status: "ok",
                gap_count: 0,
                conflict_count: 0,
                warning_count: 1,
                warnings: ["source_scope_limited"],
              },
            },
      });

      messages.push(user, assistant);
      sessionPreview = assistant.content;

      await fulfillJson(route, {
        user_message_id: user.id,
        assistant_message_id: assistant.id,
        reply: assistant.content,
        provider: "mock",
        model: "mock-model",
        key_index: null,
        usage: { input_tokens: 10, output_tokens: 20 },
        intent: isFileCommand ? "document_generation" : "rag_query",
        sources: assistant.sources,
        generated_file: assistant.generated_file,
        context_trace: assistant.context_trace,
        user_attachments: [],
        agent_run: null,
        skill_run: null,
      });
      return;
    }
    if (path === "/chat/sessions/101/export") {
      await route.fulfill({
        status: 200,
        contentType: "text/markdown",
        body: "# V2.1 收口验证\n",
      });
      return;
    }

    await fulfillJson(route, {});
  });
}

async function login(page: Page) {
  await page.addInitScript((backendUrl) => {
    window.localStorage.setItem("project-r:server-url", backendUrl as string);
    window.localStorage.setItem("project-r:onboarding-complete", "true");
  }, BACKEND_URL.replace(/\/$/, ""));

  await page.goto("/#/login");
  const enterLoginBtn = page.locator("button", { hasText: "进入登录" });
  if (await enterLoginBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await enterLoginBtn.click();
  }
  await page.locator("#username").fill("admin");
  await page.locator("#password").fill("Project_R_2026");
  await page.locator("button.alp-btn-login").click();
  await page.waitForURL("**/app**", { timeout: 15_000 });
  await expect(page.locator("textarea[placeholder*='输入消息']")).toBeVisible();
  const sessionItem = page.locator(".session-list .session-item", { hasText: "V2.1 收口验证" }).first();
  await expect(sessionItem).toBeVisible({ timeout: 5000 });
  await sessionItem.click();
  await expect(sessionItem).toHaveClass(/is-active/);
  await expect(page.locator(".chat-title-button", { hasText: "V2.1 收口验证" })).toBeEnabled();
}

test.describe("V2.1 local closure critical paths", () => {
  test.beforeEach(async ({ page }) => {
    await installMockBackend(page);
  });

  test("query mode shows scope, evidence list, and source preview without full source browsing", async ({ page }) => {
    await login(page);

    const composer = page.locator("textarea[placeholder*='输入消息']");
    await composer.fill("/query V2.1 来源范围");
    await expect(composer).toHaveValue("/query V2.1 来源范围");
    await page.getByRole("button", { name: "发送" }).click();

    await expect(page.locator(".message-sources-block")).toContainText("引用来源");
    await expect(page.locator(".message-source-item")).toContainText("V2.1 本地收口说明");
    await page.locator(".message-source-item").first().click();

    await expect(page.locator(".source-preview-body")).toContainText("本轮仅展示回答实际引用片段");
    await expect(page.locator(".source-preview-boundary")).toContainText("不提供完整知识库文件");
  });

  test("generated file card keeps personal workspace download-only boundary", async ({ page }) => {
    await login(page);

    const composer = page.locator("textarea[placeholder*='输入消息']");
    await composer.fill("/");
    await page.locator(".skill-candidate-item", { hasText: "生成 Word" }).click();
    await composer.fill("V2.1 收口记录");
    await page.getByRole("button", { name: "发送" }).click();

    const card = page.locator(".message-deliverable", { hasText: "v2-local-closure.docx" }).first();
    await expect(card).toContainText("v2-local-closure.docx");
    await expect(card.locator("button", { hasText: "下载" })).toBeVisible();
    await expect(card.locator("button", { hasText: /保存到|保存中|已保存/ })).toHaveCount(0);
  });

  test("session export entry is wired without calling real file generation", async ({ page }) => {
    await login(page);

    const exportButton = page.getByRole("button", { name: "导出对话" });
    await expect(exportButton).toBeEnabled();
    await exportButton.click();
  });
});
