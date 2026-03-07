import { Switch, Route } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Placeholder from "@/pages/Placeholder";

const queryClient = new QueryClient();

function Router() {
  return (
    <Switch>
      <Route path="/" component={Dashboard} />
      <Route path="/database" component={Placeholder} />
      <Route path="/chat" component={Placeholder} />
      <Route path="/tasks" component={Placeholder} />
      <Route path="/knowledge" component={Placeholder} />
      <Route path="/settings" component={Placeholder} />
      <Route component={Placeholder} />
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
