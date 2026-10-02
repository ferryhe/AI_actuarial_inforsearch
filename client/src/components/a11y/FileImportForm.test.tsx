import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import { FileImportForm } from "@/pages/tasks/FileImportForm";

vi.mock("@/lib/api", () => ({ apiPostForm: vi.fn(), getStoredAuthToken: vi.fn() }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["tasks.run"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
afterEach(cleanup);

it("describes the run action when no import file is selected", async () => {
  const user = userEvent.setup();
  render(<Layout><FileImportForm onSubmit={vi.fn()} submitting={false} /></Layout>);
  await user.click(screen.getByTestId("button-run-task"));
  const alert = await screen.findByTestId("text-file-upload-error");
  expect(alert).toHaveAttribute("id", "error-file-import");
  expect(alert).toHaveAttribute("role", "alert");
  expect(screen.getByTestId("button-run-task")).toHaveAttribute("aria-describedby", "error-file-import");
  expect((await axe.run(alert.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("keeps both local chooser inputs keyboard reachable and described", async () => {
  render(<Layout><FileImportForm onSubmit={vi.fn()} submitting={false} /></Layout>);
  for (const id of ["input-local-files", "input-local-directory"]) {
    const input = screen.getByTestId(id);
    expect(input).toHaveAttribute("aria-describedby", "hint-local-files");
    expect(document.getElementById("hint-local-files")?.textContent?.trim()).not.toBe("");
    (input as HTMLInputElement).focus();
    expect(document.activeElement).toBe(input);
  }
  expect((await axe.run(screen.getByTestId("input-local-files").parentElement?.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});
