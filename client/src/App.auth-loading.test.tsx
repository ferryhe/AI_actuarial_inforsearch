import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({
  apiGet,
  apiPost,
  setStoredAuthToken: vi.fn(),
  ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => { resolve = accept; });
  return { promise, resolve };
}

function setPath(path: string) {
  window.history.replaceState(null, "", path);
}

function authResponse(readOnly?: boolean) {
  return {
    data: {
      ...(readOnly === undefined ? {} : { read_only: readOnly }),
      require_auth: false,
      authenticated: false,
      user: null,
      permissions: ["files.read"],
    },
  };
}

beforeEach(() => {
  localStorage.setItem("lang", "en");
  apiGet.mockReset();
  apiPost.mockReset();
});

afterEach(() => cleanup());

describe("App auth-mode loading gate", () => {
  it.each(["/database?search=actuary&offset=20", "/file-detail?file_id=135&from=database"])(
    "does not mount either page tree at %s until the viewer mode is known",
    async (path) => {
      setPath(path);
      const auth = deferred<ReturnType<typeof authResponse>>();
      apiGet.mockImplementation((url: string) => {
        if (url === "/api/auth/me") return auth.promise;
        if (url === "/api/hub/files/135") return Promise.resolve({
          file: {
            content_version_id: 135,
            url: "https://example.org/report",
            title: "Viewer report",
            original_filename: "report.md",
            source_site: "Example Society",
            bilingual_metadata: { en: { title: "Viewer report", summary: "Summary", keywords: [] } },
            hub_categories: [],
            hub_dates: {},
            hub_date_review_status: "unannotated",
            hub_date_review_reason: "",
            source_record: {},
            annotation: { date_review_unresolved: [] },
            markdown: null,
          },
        });
        if (url.startsWith("/api/hub/files?")) return Promise.resolve({ files: [], total: 0 });
        if (url === "/api/hub/sources") return Promise.resolve({ sources: [] });
        if (url === "/api/hub/categories") return Promise.resolve({ categories: [] });
        if (url === "/api/sources") return Promise.resolve({ sources: [] });
        if (url === "/api/categories?mode=used") return Promise.resolve({ categories: [] });
        if (url.startsWith("/api/files?")) return Promise.resolve({ files: [], total: 0 });
        return Promise.resolve({});
      });

      render(<App />);
      await waitFor(() => expect(apiGet).toHaveBeenCalledWith("/api/auth/me"));
      expect(apiGet.mock.calls.map(([url]) => url)).toEqual(["/api/auth/me"]);
      expect(screen.queryByTestId("hub-read-only-banner")).not.toBeInTheDocument();
      expect(screen.queryByTestId("select-sort")).not.toBeInTheDocument();
      expect(screen.queryByTestId("hub-file-detail")).not.toBeInTheDocument();
      expect(screen.queryByTestId("nav-categories")).not.toBeInTheDocument();
      expect(screen.queryByTestId("open-sidebar")).not.toBeInTheDocument();
      expect(screen.queryByTestId("button-login")).not.toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Database Browser" })).not.toBeInTheDocument();

      auth.resolve(authResponse(true));
      expect(window.location.pathname).toBe(path.split("?", 1)[0]);
      expect(window.location.search).toBe(path.slice(path.indexOf("?")));
      if (path.startsWith("/database")) {
        expect(await screen.findByTestId("hub-read-only-banner")).toBeInTheDocument();
        await waitFor(() => expect(apiGet).toHaveBeenCalledWith(expect.stringMatching(/^\/api\/hub\/files\?/)));
      } else {
        expect(await screen.findByTestId("hub-file-detail")).toBeInTheDocument();
        expect(apiGet).toHaveBeenCalledWith("/api/hub/files/135");
        expect(apiGet).not.toHaveBeenCalledWith(expect.stringMatching(/^\/api\/files\/detail/));
      }
    },
  );

  it("mounts the normal product database after auth resolves to normal mode", async () => {
    setPath("/database");
    const auth = deferred<ReturnType<typeof authResponse>>();
    apiGet.mockImplementation((url: string) => {
      if (url === "/api/auth/me") return auth.promise;
      if (url === "/api/sources") return Promise.resolve({ sources: [] });
      if (url === "/api/categories?mode=used") return Promise.resolve({ categories: [] });
      if (url.startsWith("/api/files?")) return Promise.resolve({ files: [], total: 0, limit: 20, offset: 0 });
      return Promise.resolve({});
    });

    render(<App />);
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith("/api/auth/me"));
    expect(screen.queryByTestId("open-sidebar")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Database Browser" })).not.toBeInTheDocument();

    // A regular server does not send the viewer-only read_only field.
    auth.resolve(authResponse());
    expect(await screen.findByRole("heading", { name: "Database Browser" })).toBeInTheDocument();
    expect(screen.getByTestId("nav-categories")).toBeInTheDocument();
    expect(screen.queryByTestId("hub-read-only-banner")).not.toBeInTheDocument();
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(expect.stringMatching(/^\/api\/files\?/)));
    expect(apiGet).not.toHaveBeenCalledWith(expect.stringMatching(/^\/api\/hub\/files/));
  });

  it("replaces a Hub root redirect and keeps browser Back out of the viewer placeholder", async () => {
    window.history.replaceState(null, "", "/before-hub-root");
    window.history.pushState(null, "", "/");
    const historyLength = window.history.length;
    apiGet.mockImplementation((url: string) => {
      if (url === "/api/auth/me") return Promise.resolve(authResponse(true));
      if (url.startsWith("/api/hub/files?")) return Promise.resolve({ files: [], total: 0 });
      if (url === "/api/hub/sources") return Promise.resolve({ sources: [] });
      if (url === "/api/hub/categories") return Promise.resolve({ categories: [] });
      return Promise.resolve({});
    });

    render(<App />);
    expect(await screen.findByTestId("hub-read-only-banner")).toBeInTheDocument();
    await waitFor(() => expect(window.location.pathname).toBe("/database"));
    expect(window.history.length).toBe(historyLength);
    expect(screen.queryByText("Loading local Hub viewer…")).not.toBeInTheDocument();

    const backNavigation = new Promise<void>((resolve) => {
      window.addEventListener("popstate", () => resolve(), { once: true });
    });
    window.history.back();
    await backNavigation;
    await waitFor(() => expect(window.location.pathname).toBe("/database"));
    expect(window.history.length).toBe(historyLength);
    expect(screen.getByTestId("hub-read-only-banner")).toBeInTheDocument();
    expect(screen.queryByText("Loading local Hub viewer…")).not.toBeInTheDocument();
  });

  it("keeps both page trees closed after a network failure and retries into Hub mode", async () => {
    setPath("/database");
    const retryAuth = deferred<ReturnType<typeof authResponse>>();
    let authCalls = 0;
    apiGet.mockImplementation((url: string) => {
      if (url === "/api/auth/me") {
        authCalls += 1;
        return authCalls === 1 ? Promise.reject(new Error("network unavailable")) : retryAuth.promise;
      }
      if (url.startsWith("/api/hub/files?")) return Promise.resolve({ files: [], total: 0 });
      if (url === "/api/hub/sources") return Promise.resolve({ sources: [] });
      if (url === "/api/hub/categories") return Promise.resolve({ categories: [] });
      if (url === "/api/sources") return Promise.resolve({ sources: [] });
      if (url === "/api/categories?mode=used") return Promise.resolve({ categories: [] });
      if (url.startsWith("/api/files?")) return Promise.resolve({ files: [], total: 0 });
      return Promise.resolve({});
    });

    render(<App />);
    expect(await screen.findByTestId("auth-mode-error")).toBeInTheDocument();
    expect(screen.getByText(/Unable to connect to the local content viewer/i)).toBeInTheDocument();
    expect(screen.queryByTestId("open-sidebar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-categories")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hub-read-only-banner")).not.toBeInTheDocument();
    expect(apiGet.mock.calls.map(([url]) => url)).toEqual(["/api/auth/me"]);

    fireEvent.click(screen.getByTestId("auth-mode-retry"));
    await waitFor(() => expect(authCalls).toBe(2));
    expect(screen.queryByTestId("auth-mode-error")).not.toBeInTheDocument();
    expect(screen.getByTestId("auth-mode-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("open-sidebar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-categories")).not.toBeInTheDocument();
    expect(apiGet.mock.calls.map(([url]) => url)).toEqual(["/api/auth/me", "/api/auth/me"]);

    retryAuth.resolve(authResponse(true));
    expect(await screen.findByTestId("hub-read-only-banner")).toBeInTheDocument();
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(expect.stringMatching(/^\/api\/hub\/files\?/)));
    expect(apiGet).not.toHaveBeenCalledWith(expect.stringMatching(/^\/api\/files\?/));
  });

  it("shows a neutral error after HTTP 500 and retries into normal mode", async () => {
    setPath("/database");
    const retryAuth = deferred<ReturnType<typeof authResponse>>();
    let authCalls = 0;
    apiGet.mockImplementation((url: string) => {
      if (url === "/api/auth/me") {
        authCalls += 1;
        return authCalls === 1
          ? Promise.reject(Object.assign(new Error("internal server detail"), { status: 500 }))
          : retryAuth.promise;
      }
      if (url === "/api/sources") return Promise.resolve({ sources: [] });
      if (url === "/api/categories?mode=used") return Promise.resolve({ categories: [] });
      if (url.startsWith("/api/files?")) return Promise.resolve({ files: [], total: 0, limit: 20, offset: 0 });
      return Promise.resolve({});
    });

    render(<App />);
    expect(await screen.findByTestId("auth-mode-error")).toBeInTheDocument();
    expect(screen.queryByText(/internal server detail/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId("open-sidebar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-categories")).not.toBeInTheDocument();
    expect(apiGet.mock.calls.map(([url]) => url)).toEqual(["/api/auth/me"]);

    fireEvent.click(screen.getByTestId("auth-mode-retry"));
    await waitFor(() => expect(authCalls).toBe(2));
    expect(screen.getByTestId("auth-mode-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("open-sidebar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-categories")).not.toBeInTheDocument();
    expect(apiGet.mock.calls.map(([url]) => url)).toEqual(["/api/auth/me", "/api/auth/me"]);

    retryAuth.resolve(authResponse());
    expect(await screen.findByRole("heading", { name: "Database Browser" })).toBeInTheDocument();
    expect(screen.getByTestId("nav-categories")).toBeInTheDocument();
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(expect.stringMatching(/^\/api\/files\?/)));
    expect(apiGet).not.toHaveBeenCalledWith(expect.stringMatching(/^\/api\/hub\/files/));
  });

  it("rejects malformed auth metadata instead of assuming normal product mode", async () => {
    setPath("/database");
    const retryAuth = deferred<ReturnType<typeof authResponse>>();
    let authCalls = 0;
    apiGet.mockImplementation((url: string) => {
      if (url === "/api/auth/me") {
        authCalls += 1;
        return authCalls === 1 ? Promise.resolve({ data: {} }) : retryAuth.promise;
      }
      if (url === "/api/sources") return Promise.resolve({ sources: [] });
      if (url === "/api/categories?mode=used") return Promise.resolve({ categories: [] });
      if (url.startsWith("/api/files?")) return Promise.resolve({ files: [], total: 0, limit: 20, offset: 0 });
      return Promise.resolve({});
    });

    render(<App />);
    expect(await screen.findByTestId("auth-mode-error")).toBeInTheDocument();
    expect(screen.queryByTestId("open-sidebar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-categories")).not.toBeInTheDocument();
    expect(apiGet.mock.calls.map(([url]) => url)).toEqual(["/api/auth/me"]);

    fireEvent.click(screen.getByTestId("auth-mode-retry"));
    await waitFor(() => expect(authCalls).toBe(2));
    retryAuth.resolve(authResponse());
    expect(await screen.findByRole("heading", { name: "Database Browser" })).toBeInTheDocument();
    expect(screen.getByTestId("nav-categories")).toBeInTheDocument();
  });
});
