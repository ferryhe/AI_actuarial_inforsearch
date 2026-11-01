import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Router, Switch } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  apiGet: vi.fn(),
  translate: (key: string, values?: Record<string, string | number>) => {
    const message = ({
      "source_portals.title": "Source Portals",
      "source_portals.subtitle": "Browse directories.",
      "source_portals.load_error": "Could not load source portals",
      "source_portals.empty": "No source portals are available yet.",
      "source_portals.open_source": "Open source directory",
      "source_portals.updates": "Periodic updates",
      "source_portals.no_updates": "Future updates to this directory will be introduced here.",
      "source_portals.search_label": "Search source portals",
      "source_portals.search_placeholder": "Search by name, institution, or overview…",
      "source_portals.no_results": "No source portals match your search.",
      "source_portals.latest_update": "Latest update",
      "source_portals.no_updates_yet": "No updates yet",
      "source_portals.column_title": "Source portal",
      "source_portals.column_institution": "Institution",
      "source_portals.column_overview": "Overview",
      "source_portals.column_latest": "Latest update",
      "source_portals.pagination": "Source portal pages",
      "source_portals.previous_page": "Previous",
      "source_portals.next_page": "Next",
      "source_portals.page_label": "Page {page} of {total}",
      "source_portals.back_to_list": "Back to source portals",
      "source_portals.not_found_title": "Source portal not found",
      "source_portals.not_found_description": "This source portal is unavailable or may have been removed.",
      "common.refresh": "Refresh",
    } as Record<string, string>)[key] || key;
    return values ? message.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? `{${name}}`)) : message;
  },
}));
vi.mock("@/components/Layout", () => ({
  useTranslation: () => ({ lang: "en", t: state.translate }),
}));
vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof import("@/lib/api")>(),
  apiGet: state.apiGet,
}));

import SourcePortals, { SourcePortalDetail } from "./SourcePortals";

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

function renderPortalApp(path = "/source-portals") {
  const location = memoryLocation({ path, record: true });
  const result = render(
    <Router hook={location.hook}>
      <Switch>
        <Route path="/source-portals/:portalKey" component={SourcePortalDetail} />
        <Route path="/source-portals" component={SourcePortals} />
      </Switch>
    </Router>,
  );
  return { ...result, location };
}

function makePortal(index: number) {
  return {
    ...portal,
    portal_key: `source-${index}`,
    title_en: `Research Topic ${index}`,
    institution_en: index === 21 ? "Target Institution" : "SOA Research Group",
    overview_en: index === 21 ? "A unique phrase for this directory." : `Overview for source ${index}.`,
    updates: index === 21 ? portal.updates : [],
  };
}

beforeEach(() => {
  state.apiGet.mockReset();
});
afterEach(() => cleanup());

it("shows compact rows without exposing update prose", async () => {
  state.apiGet.mockResolvedValue({ portals: [portal, { ...portal, portal_key: "empty-history", updates: [] }] });
  renderPortalApp();

  expect(await screen.findAllByRole("link", { name: "Research Topics" })).toHaveLength(2);
  expect(screen.getAllByText("SOA's directory of materials organized by research topic.")).toHaveLength(2);
  expect(screen.getByRole("columnheader", { name: "Latest update" })).toBeInTheDocument();
  expect(screen.getByText("Nov 1, 2026")).toBeInTheDocument();
  expect(screen.getByText("No updates yet")).toBeInTheDocument();
  expect(screen.queryByText("The directory now includes “New research”.")).not.toBeInTheDocument();
  expect(screen.queryByText("SOA's directory of materials organized by research topic. You can find “AI research” here.")).not.toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Research Topics" })[0]).toHaveAttribute("href", "/source-portals/soa-research-topics");
});

it("searches names, institutions, and overviews and keeps the query in the URL", async () => {
  state.apiGet.mockResolvedValue({ portals: Array.from({ length: 21 }, (_, index) => makePortal(index + 1)) });
  const user = userEvent.setup();
  const { location } = renderPortalApp();

  expect((await screen.findAllByTestId("source-portal-row"))).toHaveLength(20);
  const search = screen.getByRole("searchbox", { name: "Search source portals" });
  fireEvent.change(search, { target: { value: "unique phrase" } });

  expect(await screen.findByRole("link", { name: "Research Topic 21" })).toBeInTheDocument();
  expect(screen.getAllByTestId("source-portal-row")).toHaveLength(1);
  expect(location.history.at(-1)).toBe("/source-portals?query=unique+phrase");
  expect(screen.queryByTestId("source-portals-pagination")).not.toBeInTheDocument();

  await user.clear(search);
  await user.type(search, "Research Topic 7");
  expect(await screen.findByRole("link", { name: "Research Topic 7" })).toBeInTheDocument();
  expect(screen.getAllByTestId("source-portal-row")).toHaveLength(1);

  await user.clear(search);
  await user.type(search, "Target Institution");
  expect(await screen.findByRole("link", { name: "Research Topic 21" })).toBeInTheDocument();
  expect(screen.getAllByTestId("source-portal-row")).toHaveLength(1);
  expect(location.history.at(-1)).toBe("/source-portals?query=Target+Institution");
});

it("paginates and returns from a detail page to the same list page", async () => {
  state.apiGet.mockResolvedValue({ portals: Array.from({ length: 21 }, (_, index) => makePortal(index + 1)) });
  const user = userEvent.setup();
  const { location } = renderPortalApp("/source-portals?page=2");

  expect(await screen.findAllByTestId("source-portal-row")).toHaveLength(1);
  expect(screen.getByTestId("source-portals-page-label")).toHaveTextContent("Page 2 of 2");
  const portalLink = screen.getByRole("link", { name: "Research Topic 21" });
  expect(portalLink).toHaveAttribute("href", "/source-portals/source-21?page=2");
  await user.click(portalLink);

  expect(await screen.findByTestId("source-portal-detail-title")).toHaveTextContent("Research Topic 21");
  expect(screen.getByText("The directory now includes “New research”.")).toBeInTheDocument();
  expect(screen.getByTestId("source-portal-original-link")).toHaveAttribute("href", portal.url);
  const backLink = screen.getByRole("link", { name: "Back to source portals" });
  expect(backLink).toHaveAttribute("href", "/source-portals?page=2");
  await user.click(backLink);

  expect(await screen.findByTestId("source-portals-page-label")).toHaveTextContent("Page 2 of 2");
  expect(screen.getAllByTestId("source-portal-row")).toHaveLength(1);
  expect(location.history.at(-1)).toBe("/source-portals?page=2");
});

it("supports direct detail routes, empty history, and a returnable not-found state", async () => {
  state.apiGet.mockResolvedValue({ portals: [{ ...portal, updates: [] }] });
  renderPortalApp("/source-portals/soa-research-topics?query=SOA&page=2");

  expect(await screen.findByTestId("source-portal-detail")).toBeInTheDocument();
  expect(screen.getByTestId("source-portal-no-updates")).toHaveTextContent("Future updates to this directory will be introduced here.");
  expect(screen.getByRole("link", { name: "Back to source portals" })).toHaveAttribute("href", "/source-portals?query=SOA&page=2");

  cleanup();
  state.apiGet.mockResolvedValue({ portals: [portal] });
  const notFoundApp = renderPortalApp("/source-portals/not-a-portal");
  expect(await screen.findByTestId("source-portal-not-found")).toHaveTextContent("Source portal not found");
  expect(screen.getByRole("link", { name: "Back to source portals" })).toHaveAttribute("href", "/source-portals");
  expect(notFoundApp.location.history[0]).toBe("/source-portals/not-a-portal");
});

it("offers a retry after the source portal request fails", async () => {
  state.apiGet.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ portals: [portal] });
  const user = userEvent.setup();
  renderPortalApp();

  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load source portals");
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  expect(await screen.findByRole("link", { name: "Research Topics" })).toBeInTheDocument();
  expect(state.apiGet).toHaveBeenCalledTimes(2);
});
