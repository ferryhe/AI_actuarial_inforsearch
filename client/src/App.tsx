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
