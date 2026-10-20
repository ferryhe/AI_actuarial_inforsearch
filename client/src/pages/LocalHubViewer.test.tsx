import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import DatabasePage from "@/pages/Database";
import FileDetail from "@/pages/FileDetail";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost: vi.fn() }));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    permissions: ["files.read"],
    isLoading: false,
    isLoggedIn: false,
    requireAuth: false,
    isReadOnlyHub: true,
    logout: vi.fn(),
  }),
}));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));

const file = {
  content_version_id: 135,
  url: "https://example.org/report",
  title: "AI report",
  original_filename: "report.md",
  source_site: "Example Society",
  first_seen: "",
  last_seen: "",
  category: "AI",
  keywords: ["AI"],
  summary: "Summary.",
  bilingual_metadata: {
    en: { title: "AI report", summary: "Summary.", category: "AI", keywords: ["AI"] },
  },
  has_markdown: true,
  markdown_source: null,
  bytes: null,
  deleted_at: null,
  hub_categories: [{
    key: "AI",
    evidence: [
      "Article title names AI",
      { quote: "A structured category quote", reason: "Category metadata is not a quote", status: "approved", value: "2099-01-01" },
    ],
  }],
  hub_dates: {
    publication_date: { value: "2025", precision: "year", evidence: "Published in the 2025 report" },
    revision_date: null,
    document_version_date: { value: "2010-12", precision: "month", evidence: ["Version header: December 2010"] },
  },
  hub_date_review_status: "candidate_limit_gap",
};

beforeEach(() => {
  localStorage.setItem("lang", "en");
  window.history.replaceState(null, "", "/database");
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/auth/me") return Promise.resolve({ data: { read_only: true, permissions: ["files.read"] } });
    if (url === "/api/hub/sources") return Promise.resolve({ sources: ["Example Society"] });
    if (url === "/api/hub/categories") return Promise.resolve({ categories: [{ name: "AI", count: 1 }] });
    if (url.startsWith("/api/hub/files?")) return Promise.resolve({ files: [file], total: 1, limit: 20, offset: 0 });
    if (url === "/api/hub/files/135") return Promise.resolve({
      file: {
        ...file,
        source_record: { legacy_file_id: "legacy-1", source_snapshot_id: 8, availability: "present" },
        annotation: {
          source_text_variant_id: 991,
          source_markdown_sha256: "b".repeat(64),
          date_review_unresolved: [{ kind: "publication_date", status: "unresolved", reason: "Year only", evidence: ["Published in 2025"], value: "2025-01-01" }],
        },
        markdown: "# Original report",
      },
    });
    return Promise.reject(new Error(`Unexpected request: ${url}`));
  });
});

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("local Hub read-only pages", () => {
  it("hides action controls, shows exact date precision, and navigates by content version ID", async () => {
    render(<Layout><DatabasePage /></Layout>);
    await screen.findByTestId("file-row-0");

    expect(screen.getByTestId("hub-read-only-banner")).toHaveTextContent("Read only");
    expect(screen.queryByTestId("button-ai-explain-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("button-ai-explain-mobile-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("button-preview-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("button-preview-mobile-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("button-download-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("button-export-csv")).not.toBeInTheDocument();
    expect(screen.queryByTestId("button-bulk-delete")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-categories")).not.toBeInTheDocument();
    expect(screen.getByTestId("text-hub-dates-0")).toHaveTextContent("Publication: 2025 (year)");
    expect(screen.getByTestId("text-hub-dates-0")).toHaveTextContent("Revision: —");
    expect(screen.getByTestId("text-hub-dates-0")).toHaveTextContent("Document version: 2010-12 (month)");

    fireEvent.click(screen.getByTestId("file-row-0"));
    await waitFor(() => expect(window.location.search).toContain("file_id=135"));
    expect(window.location.search).not.toContain("url=");
  });

  it("shows source and evidence while keeping unconfirmed normalized dates out of the detail page", async () => {
    window.history.replaceState(null, "", "/file-detail?file_id=135");
    const { container } = render(<Layout><FileDetail /></Layout>);
    await screen.findByTestId("hub-file-detail");

    expect(screen.getByTestId("link-original-url")).toHaveAttribute("href", "https://example.org/report");
    expect(screen.getByTestId("hub-date-publication_date")).toHaveTextContent("2025 (year)");
    expect(screen.getByTestId("hub-date-document_version_date")).toHaveTextContent("2010-12 (month)");
    expect(screen.getByText("No confirmed date")).toBeInTheDocument();
    expect(screen.getByText(/Published in 2025/)).toBeInTheDocument();
    expect(screen.queryByText("2025-01-01")).not.toBeInTheDocument();
    expect(screen.getByTestId("text-markdown-content")).toHaveTextContent("Original report");
    let blockquoteText = Array.from(container.querySelectorAll("blockquote"), (item) => item.textContent).join(" ");
    expect(blockquoteText).toContain("Article title names AI");
    expect(blockquoteText).toContain("A structured category quote");
    expect(blockquoteText).toContain("Published in the 2025 report");
    expect(blockquoteText).toContain("Version header: December 2010");
    expect(blockquoteText).not.toContain("Year only");
    expect(blockquoteText).not.toContain("unresolved");
    expect(blockquoteText).not.toContain("Category metadata is not a quote");
    expect(blockquoteText).not.toContain("approved");
    expect(blockquoteText).not.toContain("2099-01-01");
    expect(blockquoteText).not.toContain("publication_date");
    expect(blockquoteText).not.toContain("2025-01-01");

    fireEvent.click(screen.getByTestId("toggle-lang"));
    await screen.findByText("发布日期");
    blockquoteText = Array.from(container.querySelectorAll("blockquote"), (item) => item.textContent).join(" ");
    expect(blockquoteText).toContain("Article title names AI");
    expect(blockquoteText).toContain("A structured category quote");
    expect(blockquoteText).toContain("Published in the 2025 report");
    expect(blockquoteText).toContain("Version header: December 2010");
    for (const id of ["button-edit", "button-catalog", "button-ai-explain", "button-download", "button-preview", "button-delete", "button-md-edit", "button-modify-chunk"]) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument();
    }
  });
});
