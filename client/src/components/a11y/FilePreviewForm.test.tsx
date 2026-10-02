import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import FilePreview from "@/pages/FilePreview";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["files.download"] }) }));
const chunkContent = "# Heading\n\n- item\n\n| Name | Value |\n| --- | ---: |\n| row | 1 |\n\n```ts\nconst safe = true;\n```\n\n<script>window.xss = true</script>\n\n[javascript](javascript:alert(1))\n\n![relative](../secret.png)\n\n![missing](https://evil.example/missing.png)";

beforeEach(() => {
  window.history.pushState({}, "", "/file-preview?file_url=file-smoke");
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() });
  apiGet.mockResolvedValue({ file_info: { url: "file-smoke", original_filename: "smoke.pdf", content_type: "text/plain", bytes: 1 }, markdown: "x", chunks: [{ chunk_id: "1", chunk_index: 0, content: chunkContent, token_count: 1 }], chunk_sets: [{ chunk_set_id: "a", profile_name: "Default", chunk_count: 1 }, { chunk_set_id: "b", profile_name: "Fine", chunk_count: 1 }], active_chunk_set_id: "a" });
});

it("renders safe chunk markdown, uses image placeholders, and preserves exact source", async () => {
  const imageRequests: string[] = [];
  const originalImage = window.Image;
  window.Image = class { set src(value: string) { imageRequests.push(value); } } as typeof Image;
  try {
    render(<FilePreview />);
    expect(await screen.findByRole("heading", { name: "Heading" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("[image: relative]")).toBeInTheDocument();
    expect(screen.getByText("[image: missing]")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.queryByRole("link", { name: "javascript" })).toBeNull();
    expect(imageRequests).toEqual([]);
    fireEvent.click(screen.getByTestId("button-chunk-source"));
    expect(screen.getByTestId("chunk-source-0").textContent).toBe(chunkContent);
  } finally {
    window.Image = originalImage;
  }
});

it("names the real chunk-set selector and has no pane axe violations", async () => {
  const { container } = render(<FilePreview />);
  const select = await screen.findByTestId("select-chunk-set");
  expect(select).toHaveAttribute("aria-labelledby", "label-chunk-set");
  expect(document.getElementById("label-chunk-set")?.textContent?.trim()).not.toBe("");
  expect((await axe.run(container.querySelector('[data-testid="pane-chunks"]')!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});
