import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { MarkdownConversionTab } from "@/pages/settings/MarkdownConversionTab";

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost, ApiError: class ApiError extends Error {}, formatApiErrorDetail: () => "" }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("labels the real markdown conversion controls and has no axe violations", async () => {
  apiGet.mockResolvedValue({ config: { default_tool: "local", tools: { local: { display_name: "Local", model: "smoke" } }, formats: { pdf: { extensions: [".pdf"], candidate_chain: ["local"] } }, limits: { max_bytes: 10 } } });
  const { container } = render(<MarkdownConversionTab />);
  const select = await screen.findByTestId("select-markdown-default-tool");
  expect((select as HTMLSelectElement).labels?.[0]?.textContent?.trim()).not.toBe("");
  const model = document.getElementById("input-markdown-tool-model-local") as HTMLInputElement;
  expect(model.labels?.[0]?.textContent?.trim()).toBe("Local model");
  expect(model.labels?.[0]).not.toHaveClass("sr-only");
  expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates a failed save with its triggering action", async () => {
  apiGet.mockResolvedValue({ config: { default_tool: "local", tools: { local: { display_name: "Local" } }, formats: {}, limits: {} } });
  apiPost.mockRejectedValue(new Error("save failed"));
  const user = userEvent.setup();
  render(<MarkdownConversionTab />);
  await user.click(await screen.findByTestId("button-save-markdown-config"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-markdown-conversion");
  expect(screen.getByTestId("button-save-markdown-config")).toHaveAttribute("aria-describedby", "error-markdown-conversion");
});

it("associates a failed refresh with its triggering action", async () => {
  apiGet
    .mockResolvedValueOnce({ config: { default_tool: "local", tools: { local: { display_name: "Local" } }, formats: {}, limits: {} } })
    .mockRejectedValueOnce(new Error("refresh failed"));
  const user = userEvent.setup();
  render(<MarkdownConversionTab />);
  await user.click(await screen.findByTestId("button-refresh-markdown-config"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-markdown-conversion");
  expect(screen.getByTestId("button-refresh-markdown-config")).toHaveAttribute("aria-describedby", "error-markdown-conversion");
  expect(screen.getByTestId("button-save-markdown-config")).not.toHaveAttribute("aria-describedby");
});
