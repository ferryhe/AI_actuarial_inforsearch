import "@testing-library/jest-dom/vitest";
import axe from "axe-core";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import ConfirmDeleteModal from "@/components/ConfirmDeleteModal";

vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));

it("labels and sizes the real delete confirmation modal", async () => {
  render(<Layout><ConfirmDeleteModal open onClose={vi.fn()} onConfirm={vi.fn()} error="delete failed" /></Layout>);
  const input = screen.getByTestId("input-confirm-delete") as HTMLInputElement;
  expect(input.labels?.[0]?.textContent?.trim()).not.toBe("");
  expect(screen.getByTestId("button-execute-delete")).toHaveAttribute("aria-describedby", "error-confirm-delete");
  for (const id of ["button-close-delete-modal", "button-cancel-delete", "button-execute-delete"]) expect(screen.getByTestId(id)).toHaveClass("min-h-[48px]");
  expect((await axe.run(input.closest(".space-y-2")!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});
