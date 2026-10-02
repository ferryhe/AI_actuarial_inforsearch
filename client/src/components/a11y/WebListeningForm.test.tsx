import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import { WebListeningForm } from "@/pages/tasks/WebListeningForm";

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiPost }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["sites.write", "schedule.write"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("links a failed draft operation to its real action and has no axe violations", async () => {
  apiPost.mockRejectedValue(new Error("draft failed"));
  const user = userEvent.setup();
  const { container } = render(<Layout><WebListeningForm /></Layout>);
  await user.type(screen.getByTestId("input-web-listening-url"), "https://smoke.example");
  await user.type(screen.getByTestId("textarea-web-listening-goal"), "Monitor");
  await user.click(screen.getByTestId("button-web-listening-draft"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-web-listening-explore");
  expect(screen.getByTestId("button-web-listening-draft")).toHaveAttribute("aria-describedby", "error-web-listening-explore");
  expect(screen.getByTestId("button-web-listening-explore")).not.toHaveAttribute("aria-describedby");
  expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("links a returned Draft validation error only to Draft", async () => {
  apiPost.mockResolvedValueOnce({ success: false, valid: false, errors: ["draft invalid"] });
  const user = userEvent.setup();
  const { container } = render(<Layout><WebListeningForm /></Layout>);
  await user.type(screen.getByTestId("input-web-listening-url"), "https://smoke.example");
  await user.type(screen.getByTestId("textarea-web-listening-goal"), "Monitor");
  await user.click(screen.getByTestId("button-web-listening-draft"));
  const alert = await screen.findByTestId("text-web-listening-errors");
  expect(alert).toHaveAttribute("id", "error-web-listening-result");
  expect(alert).toHaveAttribute("role", "alert");
  expect(screen.getByTestId("button-web-listening-draft")).toHaveAttribute("aria-describedby", "error-web-listening-result");
  expect(screen.getByTestId("button-web-listening-explore")).not.toHaveAttribute("aria-describedby");
  expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});
