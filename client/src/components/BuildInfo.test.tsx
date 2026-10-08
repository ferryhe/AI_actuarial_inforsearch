import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { BuildInfo } from "./BuildInfo";

const { apiGet, permissions } = vi.hoisted(() => ({ apiGet: vi.fn(), permissions: ["logs.system.read"] }));
vi.mock("@/lib/api", () => ({ apiGet }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions }) }));
vi.mock("@/components/Layout", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); permissions.splice(0, permissions.length, "logs.system.read"); });
it("compares the complete release manifest ID and warns without blocking", async () => {
  apiGet.mockResolvedValue({ build_info: { release_manifest_id: "release-new", git_sha: "aaaaaaa" } });
  render(<BuildInfo frontend={{ release_manifest_id: "release-old", git_sha: "aaaaaaa", build_utc: "2026-10-04T12:00:00Z" }} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("settings.build_mismatch");
  expect(screen.getByTestId("frontend-release")).toHaveTextContent("release-old");
  expect(screen.getByTestId("api-release")).toHaveTextContent("release-new");
});
it("accepts matching IDs and reports unavailable identity separately", async () => {
  apiGet.mockResolvedValue({ build_info: { release_manifest_id: "release-one", git_sha: "bbbbbbb" } });
  const { unmount } = render(<BuildInfo frontend={{ release_manifest_id: "release-one", git_sha: "aaaaaaa", build_utc: "unknown" }} />);
  expect(await screen.findByText("settings.build_match")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  unmount();
  apiGet.mockResolvedValue({ build_info: { release_manifest_id: "unknown" } });
  render(<BuildInfo />);
  expect(await screen.findByRole("alert")).toHaveTextContent("settings.build_unavailable");
});
it("does not fetch or show operator build details to other roles", () => {
  permissions.length = 0;
  const { container } = render(<BuildInfo />);
  expect(container).toBeEmptyDOMElement();
  expect(apiGet).not.toHaveBeenCalled();
});
