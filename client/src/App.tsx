import { Switch, Route } from "wouter";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Database from "@/pages/Database";
import Chat from "@/pages/Chat";
import Tasks from "@/pages/Tasks";
import Knowledge from "@/pages/Knowledge";
import KBDetail from "@/pages/KBDetail";
import Settings from "@/pages/Settings";
import Logs from "@/pages/Logs";
import FileDetail from "@/pages/FileDetail";
import FilePreview from "@/pages/FilePreview";
import Users from "@/pages/Users";
import Profile from "@/pages/Profile";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import { AuthProvider } from "@/context/AuthContext";

function Router() {
  return (
    <Switch>
      {/* Auth pages — rendered without the main Layout */}
      <Route path="/login" component={Login} />
      <Route path="/register" component={Register} />

      {/* All other pages use the main Layout */}
      <Route>
        <Layout>
          <Switch>
            <Route path="/" component={Dashboard} />
            <Route path="/database" component={Database} />
            <Route path="/file-detail" component={FileDetail} />
            <Route path="/file-preview" component={FilePreview} />
            <Route path="/chat" component={Chat} />
            <Route path="/tasks" component={Tasks} />
            <Route path="/logs" component={Logs} />
            <Route path="/knowledge/:kbId" component={KBDetail} />
            <Route path="/knowledge" component={Knowledge} />
            <Route path="/settings" component={Settings} />
            <Route path="/users" component={Users} />
            <Route path="/profile" component={Profile} />
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
