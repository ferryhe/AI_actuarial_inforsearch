import { Switch, Route } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Database from "@/pages/Database";
import Chat from "@/pages/Chat";
import Tasks from "@/pages/Tasks";
import Knowledge from "@/pages/Knowledge";
import Settings from "@/pages/Settings";
import FileDetail from "@/pages/FileDetail";
import FilePreview from "@/pages/FilePreview";

const queryClient = new QueryClient();

function Router() {
  return (
    <Switch>
      <Route path="/" component={Dashboard} />
      <Route path="/database" component={Database} />
      <Route path="/file-detail" component={FileDetail} />
      <Route path="/file-preview" component={FilePreview} />
      <Route path="/chat" component={Chat} />
      <Route path="/tasks" component={Tasks} />
      <Route path="/knowledge" component={Knowledge} />
      <Route path="/settings" component={Settings} />
      <Route>
        <div className="flex items-center justify-center py-32 text-muted-foreground" data-testid="text-not-found">
          404
        </div>
      </Route>
    </Switch>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Layout>
        <Router />
      </Layout>
    </QueryClientProvider>
  );
}
