import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Link, useLocation } from "wouter";
import {
  FileText,
  BarChart3,
  Building2,
  Activity,
  Search,
  ArrowRight,
  FileIcon,
  Inbox,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";

interface Stats {
  total_files: number;
  cataloged_files: number;
  total_sources: number;
  active_tasks: number;
}

interface FileItem {
  url: string;
  title: string;
  original_filename: string;
  source_site: string;
  content_type: string;
  last_seen: string;
}

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.4, ease: "easeOut" },
  }),
};

function StatCard({
  icon: Icon,
  label,
  value,
  color,
  index,
}: {
  icon: typeof FileText;
  label: string;
  value: number | string;
  color: string;
  index: number;
}) {
  return (
    <motion.div
      custom={index}
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      className="stat-glow rounded-xl bg-card p-5 flex items-start gap-4"
      data-testid={`stat-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className={cn("w-11 h-11 rounded-xl flex items-center justify-center shrink-0", color)}>
        <Icon className="w-5 h-5" strokeWidth={1.8} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold tracking-tight font-serif">{value}</p>
        <p className="text-sm text-muted-foreground mt-0.5">{label}</p>
      </div>
    </motion.div>
  );
}

function QuickAction({
  icon: Icon,
  title,
  desc,
  href,
  color,
  index,
}: {
  icon: typeof Search;
  title: string;
  desc: string;
  href: string;
  color: string;
  index: number;
}) {
  return (
    <motion.div
      custom={index + 4}
      variants={fadeUp}
      initial="hidden"
      animate="visible"
    >
      <Link href={href}>
        <div
          className="group cursor-pointer rounded-xl border border-border bg-card p-5 hover:border-primary/30 hover:shadow-md transition-all duration-300"
          data-testid={`action-${title.toLowerCase().replace(/\s+/g, "-")}`}
        >
          <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center mb-3", color)}>
            <Icon className="w-5 h-5" strokeWidth={1.8} />
          </div>
          <h4 className="font-semibold text-sm mb-1 group-hover:text-primary transition-colors">
            {title}
          </h4>
          <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
          <ArrowRight className="w-4 h-4 mt-3 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all" />
        </div>
      </Link>
    </motion.div>
  );
}

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return dateStr;
  }
}

function contentTypeLabel(ct: string): string {
  if (!ct) return "-";
  if (ct.includes("pdf")) return "PDF";
  if (ct.includes("word") || ct.includes("document")) return "DOCX";
  if (ct.includes("presentation") || ct.includes("powerpoint")) return "PPTX";
  if (ct.includes("spreadsheet") || ct.includes("excel")) return "XLSX";
  if (ct.includes("html")) return "HTML";
  return ct.split("/").pop()?.toUpperCase() || ct;
}

export default function Dashboard() {
  const { t } = useTranslation();
  const [, navigate] = useLocation();
  const [stats, setStats] = useState<Stats | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiGet<Stats>("/api/stats"),
      apiGet<{ files: FileItem[] }>("/api/files?limit=8&order_by=last_seen&order_dir=desc"),
    ])
      .then(([statsData, filesData]) => {
        setStats(statsData);
        setFiles(filesData.files || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const statCards = [
    { icon: FileText, label: t("dashboard.total_files"), value: stats?.total_files ?? "-", color: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
    { icon: BarChart3, label: t("dashboard.cataloged"), value: stats?.cataloged_files ?? "-", color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
    { icon: Building2, label: t("dashboard.sources"), value: stats?.total_sources ?? "-", color: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
    { icon: Activity, label: t("dashboard.active_tasks"), value: stats?.active_tasks ?? "-", color: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  ];

  const quickActions = [
    { icon: Search, title: t("dashboard.browse_db"), desc: t("dashboard.browse_db_desc"), href: "/database", color: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
    { icon: Activity, title: "Task Center", desc: "Run crawls, imports, conversions, and monitor job execution.", href: "/tasks", color: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  ];

  return (
    <div className="space-y-8">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight">
          {t("dashboard.welcome")}
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
          {t("dashboard.subtitle")}
        </p>
      </motion.div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {statCards.map((card, i) => (
          <StatCard key={card.label} {...card} index={i} />
        ))}
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">{t("dashboard.quick_actions")}</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {quickActions.map((action, i) => (
            <QuickAction key={action.href} {...action} index={i} />
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">{t("dashboard.recent_files")}</h2>
        {loading ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-14 rounded-lg bg-muted animate-pulse" />
            ))}
          </div>
        ) : files.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-16 rounded-xl border border-dashed border-border bg-card"
          >
            <Inbox className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
            <p className="font-medium text-muted-foreground">{t("dashboard.no_files")}</p>
            <p className="text-xs text-muted-foreground/70 mt-1">{t("dashboard.no_files_desc")}</p>
          </motion.div>
        ) : (
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="hidden sm:grid grid-cols-[1fr_150px_80px_100px] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <span>{t("table.title")}</span>
              <span>{t("table.source")}</span>
              <span>{t("table.type")}</span>
              <span>{t("table.date")}</span>
            </div>
            {files.map((file, i) => (
              <motion.div
                key={file.url}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                className="grid sm:grid-cols-[1fr_150px_80px_100px] gap-1 sm:gap-4 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors cursor-pointer"
                onClick={() => navigate(`/file-detail?url=${encodeURIComponent(file.url)}`)}
                data-testid={`file-row-${i}`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <FileIcon className="w-4 h-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
                  <span className="text-sm font-medium truncate">
                    {file.title || file.original_filename || "Untitled"}
                  </span>
                </div>
                <span className="text-sm text-muted-foreground truncate hidden sm:block">
                  {file.source_site || "-"}
                </span>
                <span className="hidden sm:block">
                  {file.content_type && (
                    <span className="inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                      {contentTypeLabel(file.content_type)}
                    </span>
                  )}
                </span>
                <span className="text-xs text-muted-foreground hidden sm:block">
                  {formatDate(file.last_seen)}
                </span>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
