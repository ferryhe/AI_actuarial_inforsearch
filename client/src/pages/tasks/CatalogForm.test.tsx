import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { CatalogForm } from "./CatalogForm";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost: vi.fn(), formatApiErrorDetail: () => "" }));
vi.mock("@/components/Layout", () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      "tasks.form.stat_candidates": "Candidates",
      "tasks.form.stat_first_candidate": "First candidate #",
      "tasks.form.no_catalog_candidates": "没有需要编目的文件",
    }[key] || key),
  }),
}));
vi.mock("@/hooks/use-task-options", () => ({
  useTaskOptions: () => ({ categories: [], catalogProviders: ["OpenAI"] }),
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: [] }) }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function mockEmptyCandidates() {
  apiGet.mockResolvedValue({ data: {
    total_local_files: 2,
    total_catalog_ok: 2,
    candidate_total: 0,
    first_candidate_index: 7,
  } });
}

it("hides the start index and starts new Catalog tasks at the beginning", async () => {
  mockEmptyCandidates();
  const submit = vi.fn();
  const user = userEvent.setup();
  render(<CatalogForm onSubmit={submit} submitting={false} runTestId="run-catalog" />);

  expect(await screen.findByTestId("text-no-catalog-candidates")).toHaveTextContent("没有需要编目的文件");
  expect(screen.getByTestId("stats-banner")).toHaveTextContent("Candidates0");
  expect(screen.queryByText("First candidate #")).not.toBeInTheDocument();
  expect(screen.queryByTestId("input-start-index")).not.toBeInTheDocument();
  await user.clear(screen.getByTestId("input-scan-count"));
  await user.type(screen.getByTestId("input-scan-count"), "25");
  await user.click(screen.getByTestId("run-catalog"));

  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ scan_count: 25, scan_start_index: 1 }));
});

it("keeps an existing scheduled Catalog task start index in settings mode", async () => {
  mockEmptyCandidates();
  const submit = vi.fn();
  const user = userEvent.setup();
  render(
    <CatalogForm
      onSubmit={submit}
      submitting={false}
      settingsMode
      initialTask={{ scan_count: 12, scan_start_index: 9 }}
      runTestId="save-catalog"
    />,
  );

  await screen.findByTestId("text-no-catalog-candidates");
  expect(screen.queryByTestId("input-start-index")).not.toBeInTheDocument();
  await user.click(screen.getByTestId("save-catalog"));
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ scan_count: 12, scan_start_index: 9 }));
});
