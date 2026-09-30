import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Layout from "@/components/Layout";
import { IconButton } from "@/components/a11y/IconButton";
import { useI18n } from "@/hooks/use-i18n";

function DeleteSiteButton({ target }: { target: string }) {
  const { t } = useI18n();
  return <IconButton label={t("a11y.delete_site", { target })}>×</IconButton>;
}

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    isLoggedIn: false,
    logout: vi.fn(),
    permissions: ["stats.read"],
  }),
}));

vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }),
}));

beforeEach(() => localStorage.setItem("lang", "en"));
afterEach(cleanup);

describe("main navigation icon buttons", () => {
  it("has localized names, one breakpoint-specific close control, and no axe violations", async () => {
    const user = userEvent.setup();
    const { container } = render(<Layout><div>content</div></Layout>);

    expect(screen.queryByTestId("close-sidebar")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(screen.getAllByTestId("close-sidebar")).toHaveLength(1);
    const close = screen.getByRole("button", { name: "Close navigation" });
    expect(close).toBeVisible();
    const testIds = Array.from(container.querySelectorAll("[data-testid]"), (node) => node.getAttribute("data-testid"));
    expect(new Set(testIds).size).toBe(testIds.length);
    expect((await axe.run(close.closest("aside")!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
    await user.click(close);
    await waitFor(() => expect(screen.getByRole("button", { name: "Open navigation" })).toHaveFocus());
  });

  it("uses Chinese names and native keyboard activation", async () => {
    localStorage.setItem("lang", "zh");
    const user = userEvent.setup();
    const action = vi.fn();
    render(<><Layout><div>内容</div></Layout><IconButton label="删除站点 SOA" onClick={action}>×</IconButton></>);

    expect(screen.getByRole("button", { name: "打开导航" })).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "删除站点 SOA" });
    button.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(action).toHaveBeenCalledTimes(2);
    expect(button).toHaveClass("min-h-[44px]", "min-w-[44px]", "focus-visible:ring-2");
  });

  it("interpolates target objects into localized DOM names without parsing markup", () => {
    render(<DeleteSiteButton target={'SOA <prod> & "daily"'} />);
    expect(screen.getByRole("button", { name: 'Delete site SOA <prod> & "daily"' })).toBeInTheDocument();
  });
});
