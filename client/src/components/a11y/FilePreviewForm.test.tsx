import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import FilePreview from "@/pages/FilePreview";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["files.download"] }) }));

beforeEach(() => {
  window.history.pushState({}, "", "/file-preview?file_url=file-smoke");
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() });
  apiGet.mockResolvedValue({ file_info: { url: "file-smoke", original_filename: "smoke.pdf", content_type: "text/plain", bytes: 1 }, markdown: "x", chunks: [{ chunk_id: "1", chunk_index: 0, content: "x", token_count: 1 }], chunk_sets: [{ chunk_set_id: "a", profile_name: "Default", chunk_count: 1 }, { chunk_set_id: "b", profile_name: "Fine", chunk_count: 1 }], active_chunk_set_id: "a" });
});

it("names the real chunk-set selector and has no pane axe violations", async () => {
  const { container } = render(<FilePreview />);
  const select = await screen.findByTestId("select-chunk-set");
  expect(select).toHaveAttribute("aria-labelledby", "label-chunk-set");
  expect(document.getElementById("label-chunk-set")?.textContent?.trim()).not.toBe("");
  expect((await axe.run(container.querySelector('[data-testid="pane-chunks"]')!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});
