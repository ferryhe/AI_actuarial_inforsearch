import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  apiGet: vi.fn(),
  translate: (key: string) => ({
    "source_portals.title": "Source Portals",
    "source_portals.subtitle": "Browse directories.",
    "source_portals.load_error": "Could not load source portals",
    "source_portals.empty": "No source portals are available yet.",
    "source_portals.open_source": "Open source directory",
    "source_portals.updates": "Periodic updates",
    "source_portals.no_updates": "Future updates to this directory will be introduced here.",
    "common.refresh": "Refresh",
  }[key] || key),
}));
vi.mock("@/components/Layout", () => ({
  useTranslation: () => ({
    lang: "en",
    t: state.translate,
  }),
}));
vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof import("@/lib/api")>(),
  apiGet: state.apiGet,
}));

import SourcePortals from "./SourcePortals";

const portal = {
  portal_key: "soa-research-topics",
  url: "https://www.soa.org/research/research-topic-list/",
  title_zh: "研究主题目录",
  title_en: "Research Topics",
  institution_zh: "美国精算师协会（SOA）",
  institution_en: "Society of Actuaries (SOA)",
  overview_zh: "汇集 SOA 按研究主题整理的资料入口。",
  overview_en: "SOA's directory of materials organized by research topic.",
  updates: [
    {
      acquired_on: "2026-11-01",
      description_zh: "这次多了「研究新进展」，可以从入口继续阅读。",
      description_en: "The directory now includes “New research”.",
    },
    {
      acquired_on: "2026-10-31",
      description_zh: "汇集 SOA 按研究主题整理的资料入口。这里可以找到「AI 精算研究」资料。",
      description_en: "SOA's directory of materials organized by research topic. You can find “AI research” here.",
    },
  ],
};

beforeEach(() => {
  state.apiGet.mockReset();
});
afterEach(() => cleanup());

it("renders persisted prose newest first without system identifiers or counters", async () => {
  state.apiGet.mockResolvedValue({ portals: [portal] });
  render(<SourcePortals />);

  expect(await screen.findByText("Research Topics")).toBeInTheDocument();
  expect(screen.getByText("The directory now includes “New research”.")).toBeInTheDocument();
  expect(screen.getByText("SOA's directory of materials organized by research topic. You can find “AI research” here.")).toBeInTheDocument();
  expect(screen.getByText("Nov 1, 2026")).toBeInTheDocument();
  expect(screen.getByText("Oct 31, 2026")).toBeInTheDocument();
  expect(screen.queryByText(/capture_id|version_id|\bcount\b/i)).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open source directory Research Topics" })).toHaveAttribute(
    "href",
    portal.url,
  );
});

it("shows an empty-history card and a retryable API error", async () => {
  state.apiGet.mockResolvedValueOnce({ portals: [{ ...portal, updates: [] }] });
  render(<SourcePortals />);
  expect(await screen.findByText("Future updates to this directory will be introduced here.")).toBeInTheDocument();

  cleanup();
  state.apiGet.mockRejectedValue(new Error("offline"));
  render(<SourcePortals />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load source portals");
  expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
});
