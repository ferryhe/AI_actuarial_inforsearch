import { Switch, Route } from "wouter";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Database from "@/pages/Database";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import FeatureUnavailable from "@/pages/FeatureUnavailable";
import FileDetail from "@/pages/FileDetail";
import FilePreview from "@/pages/FilePreview";
import NativeLogs from "@/pages/NativeLogs";
import NativeSettings from "@/pages/NativeSettings";
import Tasks from "@/pages/Tasks";

/** Redirects to /login when require_auth is enabled and the user is not signed in. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isLoading, isLoggedIn, requireAuth } = useAuth();
  if (isLoading) return null;
  if (requireAuth && !isLoggedIn) {
    return (
      <FeatureUnavailable
        title="Authentication is required"
        description="This environment requires authentication, but the FastAPI-native shell does not expose legacy sign-in flows. Please disable auth for native QA or finish the native auth migration first."
      />
    );
  }
  return <>{children}</>;
}

function Router() {
  return (
    <Switch>
      <Route path="/login">
        <FeatureUnavailable
          title="Sign in is not available in FastAPI-native mode"
          description="This React shell only exposes flows that are implemented natively in FastAPI."
        />
      </Route>
      <Route path="/register">
        <FeatureUnavailable
          title="Registration is not available in FastAPI-native mode"
          description="This React shell only exposes flows that are implemented natively in FastAPI."
        />
      </Route>

      <Route>
        <RequireAuth>
          <Layout>
            <Switch>
              <Route path="/" component={Dashboard} />
              <Route path="/database" component={Database} />
              <Route path="/file-detail" component={FileDetail} />
              <Route path="/file-preview" component={FilePreview} />
              <Route path="/chat">
                <FeatureUnavailable title="Chat is not available in FastAPI-native mode" description="The chat workflow still depends on legacy APIs and is intentionally hidden from the native shell." />
              </Route>
              <Route path="/tasks" component={Tasks} />
              <Route path="/logs" component={NativeLogs} />
              <Route path="/knowledge/:kbId">
                <FeatureUnavailable title="Knowledge Bases are not available in FastAPI-native mode" description="Knowledge base management still depends on legacy APIs and is intentionally hidden from the native shell." />
              </Route>
              <Route path="/knowledge">
                <FeatureUnavailable title="Knowledge Bases are not available in FastAPI-native mode" description="Knowledge base management still depends on legacy APIs and is intentionally hidden from the native shell." />
              </Route>
              <Route path="/settings" component={NativeSettings} />
              <Route path="/users">
                <FeatureUnavailable title="User management is not available in FastAPI-native mode" description="User management still depends on legacy APIs and is intentionally hidden from the native shell." />
              </Route>
              <Route path="/profile">
                <FeatureUnavailable title="Profile is not available in FastAPI-native mode" description="Profile management still depends on legacy APIs and is intentionally hidden from the native shell." />
              </Route>
              <Route>
                <div className="flex items-center justify-center py-32 text-muted-foreground" data-testid="text-not-found">
                  404
                </div>
              </Route>
            </Switch>
          </Layout>
        </RequireAuth>
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
