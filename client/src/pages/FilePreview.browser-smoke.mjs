import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5180";
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const preview = {
  file_info: { url: "file-smoke", original_filename: "smoke.txt", content_type: "text/plain", bytes: 1 },
  markdown: { content: "", source: "", updated_at: "" },
  chunks: [{ chunk_id: "1", chunk_index: 0, token_count: 1, content: `# Heading

- item

| Name | Value |
| --- | ---: |
| row | 1 |

\`\`\`ts
const safe = true;
\`\`\`

<script>window.xss = true</script>

[javascript](javascript:alert(1))

![relative](../secret.png)

![missing](https://evil.example/missing.png)

${"verylongword".repeat(30)}`, chunk_set_id: "a" }],
  chunk_sets: [
    { chunk_set_id: "a", profile_name: "Default", chunk_count: 1 },
    { chunk_set_id: "b", profile_name: "Long valid profile name for a responsive chunk preview selector", chunk_count: 1 },
  ], active_chunk_set_id: "a",
};

try {
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }, { width: 320, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    const requests = [];
    page.on("request", (request) => requests.push(request.url()));
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const body = path === "/api/auth/me" ? { data: { require_auth: false, authenticated: false, permissions: [] } } : preview;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto(`${baseUrl}/file-preview?file_url=file-smoke`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Heading" }).waitFor();
    assert.equal(await page.getByRole("table").count(), 1);
    assert.equal(await page.getByTestId("pane-chunks").locator("script").count(), 0);
    assert.equal(await page.getByRole("link", { name: "javascript" }).count(), 0);
    assert.equal(await page.getByText("[image: relative]").count(), 1);
    assert.equal(await page.getByText("[image: missing]").count(), 1);
    assert.equal(requests.some((url) => url.includes("evil.example") || url.includes("secret.png")), false);
    await page.getByTestId("button-chunk-source").click();
    await page.getByTestId("chunk-source-0").waitFor();
    assert.match(await page.getByTestId("chunk-source-0").textContent(), /<script>window\.xss = true<\/script>/);
    const original = await page.getByTestId("pane-original").boundingBox();
    const chunks = await page.getByTestId("pane-chunks").boundingBox();
    assert.ok(original && chunks && (viewport.width > 1024 ? Math.abs(original.y - chunks.y) < 2 : chunks.y > original.y));
    await page.getByTestId("button-chunk-source").waitFor();
    const selector = await page.getByTestId("select-chunk-set").boundingBox();
    assert.ok(selector && chunks && selector.x >= chunks.x && selector.x + selector.width <= chunks.x + chunks.width);
    await page.close();
  }
  console.log("File Preview Chromium smoke passed");
} finally {
  await browser.close();
}
