import { useEffect } from "react";
import { Switch, Route, useLocation } from "wouter";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Database from "@/pages/Database";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Chat from "@/pages/Chat";
import FileDetail from "@/pages/FileDetail";
import FilePreview from "@/pages/FilePreview";
import KBDetail from "@/pages/KBDetail";
import Knowledge from "@/pages/Knowledge";
import Login from "@/pages/Login";
import NativeLogs from "@/pages/NativeLogs";
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

function Router() {
  return (
    <Switch>
      <Route path="/login" component={Login} />
      <Route path="/register" component={Register} />
      <Route>
        <Layout>
          <Switch>
            <Route path="/" component={Dashboard} />
            <Route path="/database" component={Database} />
            <Route path="/file-detail" component={FileDetail} />
            <Route path="/file-preview" component={FilePreview} />
            <Route path="/chat" component={Chat} />
            <Route path="/tasks">
              <RequireAuth>
                <Tasks />
              </RequireAuth>
            </Route>
            <Route path="/logs">
              <RequireAuth>
                <NativeLogs />
              </RequireAuth>
            </Route>
            <Route path="/knowledge/:kbId">
              <RequireAuth>
                <KBDetail />
              </RequireAuth>
            </Route>
            <Route path="/knowledge">
              <RequireAuth>
                <Knowledge />
              </RequireAuth>
            </Route>
            <Route path="/settings">
              <RequireAuth>
                <SettingsPage />
              </RequireAuth>
            </Route>
            <Route path="/users">
              <RequireAuth>
                <Users />
              </RequireAuth>
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
