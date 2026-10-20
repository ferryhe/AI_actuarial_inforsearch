import { useEffect } from "react";
import { Switch, Route, useLocation } from "wouter";
import Layout from "@/components/Layout";
import Categories from "@/pages/Categories";
import Dashboard from "@/pages/Dashboard";
import Database from "@/pages/Database";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Chat from "@/pages/Chat";
import FileDetail from "@/pages/FileDetail";
import FilePreview from "@/pages/FilePreview";
import KBDetail from "@/pages/KBDetail";
import Knowledge from "@/pages/Knowledge";
import Login from "@/pages/Login";
import LogsPage from "@/pages/Logs";
import Profile from "@/pages/Profile";
import Register from "@/pages/Register";
import SettingsPage from "@/pages/Settings";
import Tasks from "@/pages/Tasks";
import Users from "@/pages/Users";
import Weekly from "@/pages/Weekly";

/** Redirects to /login when require_auth is enabled and the user is not signed in. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isLoading, isLoggedIn, requireAuth } = useAuth();
  const [, navigate] = useLocation();

  useEffect(() => {
    if (!isLoading && requireAuth && !isLoggedIn) {
      navigate("/login");
    }
  }, [isLoading, requireAuth, isLoggedIn, navigate]);

  if (isLoading) return null;
  if (requireAuth && !isLoggedIn) {
    return null;
  }
  return <>{children}</>;
}

function RequirePermission({ permission, children }: { permission: string; children: React.ReactNode }) {
  const { isLoading, permissions, requireAuth, isLoggedIn } = useAuth();
  const [, navigate] = useLocation();
  const hasPermission = permissions.includes(permission);

  useEffect(() => {
    if (!isLoading && requireAuth && !isLoggedIn && !hasPermission) {
      navigate("/login");
    }
  }, [isLoading, requireAuth, isLoggedIn, hasPermission, navigate]);

  if (isLoading) return null;
  if (requireAuth && !isLoggedIn && !hasPermission) return null;
  if (!hasPermission) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-sm text-muted-foreground" data-testid="text-forbidden">
        403 — insufficient permissions
      </div>
    );
  }
  return <>{children}</>;
}

function Router() {
  const { isReadOnlyHub, isLoading, authError, refresh } = useAuth();
  const [location, navigate] = useLocation();

  useEffect(() => {
    if (!isLoading && isReadOnlyHub && location !== "/database" && location !== "/file-detail") {
      navigate("/database", { replace: true });
    }
  }, [isLoading, isReadOnlyHub, location, navigate]);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-muted-foreground" role="status" data-testid="auth-mode-loading">
        Connecting to the local content viewer… / 正在连接本地内容浏览器…
      </main>
    );
  }

  if (authError) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center" role="alert" data-testid="auth-mode-error">
        <p className="text-sm text-muted-foreground">
          Unable to connect to the local content viewer. Please retry. / 无法连接到本地内容浏览器，请重试。
        </p>
        <button
          type="button"
          className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium hover:bg-muted"
          data-testid="auth-mode-retry"
          onClick={() => void refresh()}
        >
          Retry / 重试
        </button>
      </main>
    );
  }

  if (isReadOnlyHub) {
    return (
      <Layout>
        <Switch>
          <Route path="/database" component={Database} />
          <Route path="/file-detail" component={FileDetail} />
          <Route>
            <div className="flex min-h-[50vh] items-center justify-center text-sm text-muted-foreground">Loading local Hub viewer…</div>
          </Route>
        </Switch>
      </Layout>
    );
  }

  return (
    <Switch>
      <Route path="/login" component={Login} />
      <Route path="/register" component={Register} />
      <Route>
        <Layout>
          <Switch>
            <Route path="/">
              <RequirePermission permission="stats.read">
                <Dashboard />
              </RequirePermission>
            </Route>
            <Route path="/database" component={Database} />
            <Route path="/weekly">
              <RequirePermission permission="files.read">
                <Weekly />
              </RequirePermission>
            </Route>
            <Route path="/categories">
              <RequirePermission permission="files.read">
                <Categories />
              </RequirePermission>
            </Route>
            <Route path="/file-detail" component={FileDetail} />
            <Route path="/file-preview" component={FilePreview} />
            <Route path="/chat" component={Chat} />
            <Route path="/tasks">
              <RequirePermission permission="tasks.view">
                <Tasks />
              </RequirePermission>
            </Route>
            <Route path="/logs">
              <RequirePermission permission="logs.task.read">
                <LogsPage />
              </RequirePermission>
            </Route>
            <Route path="/knowledge/:kbId">
              <RequirePermission permission="catalog.read">
                <KBDetail />
              </RequirePermission>
            </Route>
            <Route path="/knowledge">
              <RequirePermission permission="catalog.read">
                <Knowledge />
              </RequirePermission>
            </Route>
            <Route path="/settings">
              <RequirePermission permission="config.write">
                <SettingsPage />
              </RequirePermission>
            </Route>
            <Route path="/users">
              <RequirePermission permission="users.manage">
                <Users />
              </RequirePermission>
            </Route>
            <Route path="/profile">
              <RequireAuth>
                <Profile />
              </RequireAuth>
            </Route>
            <Route>
              <div className="flex items-center justify-center py-32 text-muted-foreground" data-testid="text-not-found">
                404
              </div>
            </Route>
          </Switch>
        </Layout>
      </Route>
    </Switch>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Router />
    </AuthProvider>
  );
}
