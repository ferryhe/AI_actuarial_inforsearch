import { Link, useLocation } from "wouter";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Database,
  MessageSquare,
  ListTodo,
  BookOpen,
  Settings,
  Sun,
  Moon,
  Languages,
  Menu,
  X,
  Users,
  ScrollText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/hooks/use-theme";
import { useI18n } from "@/hooks/use-i18n";
import { useState, createContext, useContext } from "react";

const I18nContext = createContext<ReturnType<typeof useI18n>>({
  lang: "en",
  t: (k: string) => k,
  toggleLang: () => {},
});

export function useTranslation() {
  return useContext(I18nContext);
}

const navItems = [
  { path: "/", icon: LayoutDashboard, labelKey: "nav.dashboard" },
  { path: "/database", icon: Database, labelKey: "nav.database" },
  { path: "/chat", icon: MessageSquare, labelKey: "nav.chat" },
  { path: "/tasks", icon: ListTodo, labelKey: "nav.tasks" },
  { path: "/logs", icon: ScrollText, labelKey: "nav.logs" },
  { path: "/knowledge", icon: BookOpen, labelKey: "nav.knowledge" },
  { path: "/users", icon: Users, labelKey: "nav.users" },
  { path: "/settings", icon: Settings, labelKey: "nav.settings" },
];

function Sidebar({ collapsed, onClose }: { collapsed: boolean; onClose: () => void }) {
  const [location] = useLocation();
  const { t } = useTranslation();

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex flex-col bg-card border-r border-border transition-all duration-300",
        collapsed ? "w-16" : "w-60",
        "lg:relative"
      )}
    >
      <div className="flex items-center gap-3 px-4 h-16 border-b border-border shrink-0">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center shrink-0">
          <BookOpen className="w-4 h-4 text-primary-foreground" />
        </div>
        {!collapsed && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="font-serif font-bold text-sm tracking-tight truncate"
          >
            {t("nav.brand")}
          </motion.span>
        )}
        <button
          onClick={onClose}
          className="lg:hidden ml-auto p-1 rounded hover:bg-muted"
          data-testid="close-sidebar"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(({ path, icon: Icon, labelKey }) => {
          const active = location === path || (path !== "/" && location.startsWith(path));
          return (
            <Link key={path} href={path}>
              <div
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all cursor-pointer",
                  active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                )}
                data-testid={`nav-${labelKey.split(".")[1]}`}
              >
                <Icon className={cn("w-[18px] h-[18px] shrink-0", active && "text-primary")} strokeWidth={active ? 2.2 : 1.8} />
                {!collapsed && <span className="truncate">{t(labelKey)}</span>}
              </div>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const i18n = useI18n();
  const { theme, toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <I18nContext.Provider value={i18n}>
      <div className="flex h-screen overflow-hidden">
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        <div className={cn("hidden lg:flex")}>
          <Sidebar collapsed={false} onClose={() => setSidebarOpen(false)} />
        </div>

        {sidebarOpen && (
          <div className="lg:hidden">
            <Sidebar collapsed={false} onClose={() => setSidebarOpen(false)} />
          </div>
        )}

        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-14 border-b border-border flex items-center justify-between px-4 bg-card/80 backdrop-blur-sm shrink-0">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 -ml-2 rounded-lg hover:bg-muted"
              data-testid="open-sidebar"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex-1" />
            <div className="flex items-center gap-1">
              <button
                onClick={i18n.toggleLang}
                className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground text-xs font-semibold transition-colors"
                data-testid="toggle-lang"
                title="Switch language"
              >
                {i18n.t("lang.toggle")}
              </button>
              <button
                onClick={toggleTheme}
                className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                data-testid="toggle-theme"
                title={i18n.t("theme.toggle")}
              >
                {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </button>
            </div>
          </header>

          <main className="flex-1 overflow-y-auto">
            <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
              {children}
            </div>
          </main>
        </div>
      </div>
    </I18nContext.Provider>
  );
}
