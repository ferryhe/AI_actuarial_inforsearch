import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const kb = {
  kb_id: "kb-smoke",
  id: "kb-smoke",
  name: "Smoke KB",
  description: "Smoke detail",
  kb_mode: "category",
  chunk_profile_id: "profile-smoke",
  file_count: 0,
  document_count: 0,
};
const reembedKb = { ...kb, kb_id: "kb-reembed", id: "kb-reembed", name: "Reembed KB", reason: "embedding_incompatible" };
const manifest = {
  kb_id: "kb-smoke",
  profile: "general",
  status: "ready",
  automation_state: "awaiting_publish",
  automatic_build_enabled: true,
  automatic_publish_enabled: false,
  last_attempt_publication_id: "attempt-smoke",
  publication_state: {
    active_publication_id: "active-smoke",
    previous_publication_id: "previous-smoke",
    active_publication: { publication_id: "active-smoke", status: "active" },
    previous_publication: { publication_id: "previous-smoke", status: "previous" },
  },
};
const file = {
  file_url: "smoke-file",
  title: "Smoke file",
  category: "Smoke",
  source_site: "test",
};
const browser = await chromium.launch({
  executablePath:
    process.env.CHROME_PATH ||
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});

async function stub(route, user) {
  const path = new URL(route.request().url()).pathname;
  const body =
    path === "/api/auth/me"
      ? {
          data: {
            require_auth: true,
            authenticated: true,
            user: {
              id: 1,
              email: `${user.role}@example.test`,
              display_name: user.role,
              role: user.role,
              is_active: true,
            },
            permissions: user.permissions,
          },
        }
      : path === "/api/rag/knowledge-bases"
        ? { knowledge_bases: [{ ...kb, agentic_ready_manifest: manifest }, reembedKb] }
        : path === "/api/rag/knowledge-bases/kb-smoke"
          ? { knowledge_base: kb }
          : path === "/api/rag/knowledge-bases/kb-reembed"
            ? { knowledge_base: reembedKb }
          : path.endsWith("/stats")
            ? { file_count: 1, pending_count: 1 }
            : path.endsWith("/files")
              ? { files: [file], total_files: 1 }
              : path.endsWith("/categories")
                ? { categories: [{ name: "Smoke", file_count: 1 }] }
                : path.endsWith("agentic-ready-manifest")
                  ? { manifest }
                  : path === "/api/chunk/profiles"
                    ? {
                        profiles: [
                          {
                            profile_id: "profile-smoke",
                            name: "Smoke profile",
                            chunk_size: 100,
                            chunk_overlap: 10,
                          },
                        ],
                      }
                    : { categories: [] };
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

try {
  for (const user of [
    { role: "guest", permissions: ["catalog.read"] },
    { role: "registered", permissions: ["catalog.read"] },
    { role: "catalog-only", permissions: ["catalog.read", "catalog.write"] },
    {
      role: "operator",
      permissions: ["catalog.read", "catalog.write", "tasks.run"],
    },
    {
      role: "admin",
      permissions: [
        "catalog.read",
        "catalog.write",
        "tasks.run",
        "config.write",
      ],
    },
  ]) {
    const canCatalog = user.permissions.includes("catalog.write");
    const canTasks = user.permissions.includes("tasks.run");
    const canConfig = user.permissions.includes("config.write");
    const page = await browser.newPage();
    await page.route("**/api/**", (route) => stub(route, user));
    if (user.role === "operator" || user.role === "admin") {
      await page.goto(baseUrl, { waitUntil: "networkidle" });
      await page.getByTestId("nav-knowledge").click();
      await page.getByTestId("button-create-kb").waitFor();
    } else {
      await page.goto(`${baseUrl}/knowledge`, { waitUntil: "networkidle" });
    }
    assert.equal(
      await page.getByTestId("button-create-kb").count(),
      canCatalog ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-delete-kb-kb-smoke").count(),
      canCatalog ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-reembed-kb-kb-reembed").count(),
      canTasks ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-create-profile").count(),
      canConfig ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-toggle-cleanup").count(),
      canConfig ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-delete-profile-0").count(),
      canConfig ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-build-agentic-manifest-kb-smoke").count(),
      canTasks ? 1 : 0,
    );
    if (canCatalog) {
      await page.getByTestId("button-create-kb").click();
      await page.getByTestId("button-submit-kb").waitFor();
      assert.equal(
        await page.getByTestId("button-submit-kb-index").count(),
        canTasks ? 1 : 0,
      );
      if (user.role === "catalog-only") {
        await page.getByTestId("select-kb-mode").selectOption("all");
        await page.getByTestId("input-kb-name").fill("Catalog only KB");
        assert.equal(await page.getByTestId("button-submit-kb").isDisabled(), false);
        await page.getByTestId("button-submit-kb").click();
        await page.getByTestId("alert-kb-action-notice").waitFor();
      }
    }
    if (canConfig) {
      await page.getByTestId("button-create-profile").click();
      await page.getByTestId("button-submit-profile").waitFor();
      await page.getByTestId("button-toggle-cleanup").click();
    }
    assert.equal(
      await page.getByTestId("button-run-cleanup").count(),
      canConfig ? 1 : 0,
    );
    if (user.role === "operator" || user.role === "admin") {
      await page.getByTestId("button-view-kb-kb-smoke").click();
      await page.getByTestId("text-kb-name").waitFor();
    } else {
      await page.goto(`${baseUrl}/knowledge/kb-smoke`, {
        waitUntil: "networkidle",
      });
    }
    await page.getByTestId("text-kb-name").waitFor();
    assert.equal(
      await page.getByTestId("input-kb-edit-name").count(),
      canCatalog ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-add-category").count(),
      canCatalog ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-bind-files").count(),
      canCatalog ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-remove-file-0").count(),
      canCatalog ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-remove-category-Smoke").count(),
      canCatalog ? 1 : 0,
    );
    if (canCatalog) {
      await page.getByTestId("input-kb-edit-name").fill("Updated smoke KB");
      await page.getByTestId("button-save-kb").waitFor();
      await page.getByTestId("button-add-category").click();
      await page.getByTestId("button-submit-category").waitFor();
      await page.getByTestId("button-bind-files").click();
      await page.getByTestId("button-submit-bind").waitFor();
    } else {
      assert.equal(await page.getByTestId("button-submit-bind").count(), 0);
    }
    assert.equal(
      await page.getByTestId("button-index-incremental").count(),
      canTasks ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-index-rebuild").count(),
      canTasks ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-build-agentic-manifest-detail").count(),
      canTasks ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-category-index-now").count(),
      canTasks ? 1 : 0,
    );
    assert.equal(await page.getByTestId("button-view-pending").count(), canTasks ? 1 : 0);
    assert.equal(
      await page.getByTestId("button-publish-ready-data").count(),
      canTasks ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("button-rollback-ready-data").count(),
      canTasks ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("toggle-ready-data-automatic-build").count(),
      canTasks ? 1 : 0,
    );
    assert.equal(
      await page.getByTestId("toggle-ready-data-automatic-publish").count(),
      canTasks ? 1 : 0,
    );
    await page.goto(`${baseUrl}/knowledge/kb-reembed`, { waitUntil: "networkidle" });
    await page.getByTestId("text-kb-name").waitFor();
    assert.equal(
      await page.getByTestId("button-reembed-current-embedding").count(),
      canTasks ? 1 : 0,
    );
    console.log(
      JSON.stringify({
        role: user.role,
        catalogWrite: canCatalog,
        tasksRun: canTasks,
        configWrite: canConfig,
      }),
    );
    await page.close();
  }
} finally {
  await browser.close();
}
