import { useEffect, useState, useCallback } from "react";
import {
  User,
  Shield,
  ShieldCheck,
  Clock,
  BarChart2,
  Settings,
  Loader2,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPatch } from "@/lib/api";

interface UserProfile {
  id: number | null;
  email: string | null;
  display_name: string;
  role: string;
  is_active: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

interface Quota {
  used: number;
  limit: number;
  remaining: number;
  date: string;
}

interface ActivityEntry {
  id: number;
  action: string;
  resource?: string;
  detail?: string;
  created_at?: string;
  ip_address?: string;
}

interface ProfileData {
  user: UserProfile;
  quota: Quota;
  recent_activity: ActivityEntry[];
}

const ROLE_COLORS: Record<string, string> = {
  admin: "bg-red-500/10 text-red-600 dark:text-red-400",
  premium: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  operator: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  operator_ai: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  registered: "bg-green-500/10 text-green-600 dark:text-green-400",
};

export default function ProfilePage() {
  const { t } = useTranslation();
  const [data, setData] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState(false);

  // Settings form state
  const [displayName, setDisplayName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchProfile = useCallback(async () => {
    setLoading(true);
    setAuthError(false);
    try {
      const result = await apiGet<ProfileData & { success?: boolean }>("/api/user/me");
      setData(result);
      setDisplayName(result.user?.display_name || "");
    } catch (e: any) {
      if (e.status === 401 || e.message?.includes("401") || e.message?.includes("authenticated")) {
        setAuthError(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveMessage(null);
    try {
      const body: Record<string, string> = {};
      if (data?.user?.display_name !== displayName) {
        body.display_name = displayName;
      }
      if (newPassword) {
        body.current_password = currentPassword;
        body.new_password = newPassword;
      }
      if (Object.keys(body).length === 0) {
        setSaveMessage({ type: "error", text: t("profile.no_changes") });
        return;
      }
      await apiPatch("/api/user/profile", body);
      setSaveMessage({ type: "success", text: t("profile.save_success") });
      setCurrentPassword("");
      setNewPassword("");
      await fetchProfile();
    } catch (e: any) {
      setSaveMessage({ type: "error", text: e.message || t("profile.save_error") });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (authError || !data) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("profile.title")}</h1>
          <p className="text-muted-foreground text-sm mt-1">{t("profile.subtitle")}</p>
        </div>
        <div className="bg-muted rounded-lg p-8 text-center text-muted-foreground">
          <User className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>{t("profile.not_logged_in")}</p>
          <a href="/email-login" className="mt-3 inline-block text-primary underline text-sm">
            {t("profile.login_link")}
          </a>
        </div>
      </div>
    );
  }

  const { user, quota, recent_activity } = data;
  const quotaPct = quota.limit > 0 ? Math.min(100, (quota.used / quota.limit) * 100) : 0;
  const roleColor = ROLE_COLORS[user.role] ?? ROLE_COLORS.registered;

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight" data-testid="text-profile-title">
          {t("profile.title")}
        </h1>
        <p className="text-muted-foreground text-sm mt-1">{t("profile.subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Account info card */}
        <div className="bg-card border border-border rounded-xl p-5" data-testid="card-account-info">
          <div className="flex items-center gap-2 mb-4">
            <User className="w-4 h-4 text-muted-foreground" />
            <h2 className="font-semibold text-sm">{t("profile.account")}</h2>
          </div>
          <dl className="space-y-3 text-sm">
            {user.email && (
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{t("profile.email")}</dt>
                <dd className="font-medium truncate">{user.email}</dd>
              </div>
            )}
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{t("profile.display_name")}</dt>
              <dd className="font-medium">{user.display_name || "—"}</dd>
            </div>
            <div className="flex justify-between gap-2 items-center">
              <dt className="text-muted-foreground">{t("profile.role")}</dt>
              <dd>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-semibold",
                    roleColor
                  )}
                  data-testid="badge-role"
                >
                  {user.role === "admin" ? (
                    <ShieldCheck className="w-3.5 h-3.5" />
                  ) : (
                    <Shield className="w-3.5 h-3.5" />
                  )}
                  {user.role}
                </span>
              </dd>
            </div>
            {user.created_at && (
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{t("profile.member_since")}</dt>
                <dd className="text-xs">{user.created_at.slice(0, 10)}</dd>
              </div>
            )}
            {user.last_login_at && (
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{t("profile.last_login")}</dt>
                <dd className="text-xs">{user.last_login_at.slice(0, 19).replace("T", " ")}</dd>
              </div>
            )}
          </dl>
        </div>

        {/* Quota card */}
        <div className="bg-card border border-border rounded-xl p-5" data-testid="card-quota">
          <div className="flex items-center gap-2 mb-4">
            <BarChart2 className="w-4 h-4 text-muted-foreground" />
            <h2 className="font-semibold text-sm">
              {t("profile.quota")} — {quota.date}
            </h2>
          </div>
          <div className="text-3xl font-bold mb-1" data-testid="text-quota-used">
            {quota.used}{" "}
            <span className="text-base font-normal text-muted-foreground">/ {quota.limit}</span>
          </div>
          <div className="h-2.5 rounded-full bg-muted overflow-hidden my-2">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                quotaPct >= 80
                  ? "bg-gradient-to-r from-amber-500 to-red-500"
                  : "bg-gradient-to-r from-blue-500 to-emerald-500"
              )}
              style={{ width: `${quotaPct}%` }}
              data-testid="quota-bar"
            />
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {quota.remaining} {t("profile.quota_remaining")}
          </p>
          {user.role === "registered" && (
            <a
              href="/upgrade"
              className="mt-3 inline-block text-xs text-primary hover:underline"
            >
              {t("profile.upgrade")}
            </a>
          )}
        </div>

        {/* Recent Activity */}
        <div className="bg-card border border-border rounded-xl p-5 md:col-span-2" data-testid="card-activity">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-4 h-4 text-muted-foreground" />
            <h2 className="font-semibold text-sm">{t("profile.activity")}</h2>
          </div>
          {recent_activity.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("profile.no_activity")}</p>
          ) : (
            <div className="space-y-2">
              {recent_activity.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-start gap-3 text-sm border-b border-border pb-2 last:border-0"
                  data-testid={`activity-${entry.id}`}
                >
                  <div className="flex-1 min-w-0">
                    <span className="font-medium">{entry.action}</span>
                    {entry.detail && (
                      <span className="text-muted-foreground text-xs ml-2">{entry.detail}</span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                    {(entry.created_at || "").slice(0, 19).replace("T", " ")}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Settings */}
        {user.id !== null && (
          <div className="bg-card border border-border rounded-xl p-5 md:col-span-2" data-testid="card-settings">
            <div className="flex items-center gap-2 mb-4">
              <Settings className="w-4 h-4 text-muted-foreground" />
              <h2 className="font-semibold text-sm">{t("profile.settings")}</h2>
            </div>
            <form onSubmit={handleSave} className="space-y-4 max-w-md">
              <div>
                <label className="block text-sm font-medium mb-1">
                  {t("profile.display_name_label")}
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  maxLength={100}
                  placeholder={t("profile.display_name_placeholder")}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/50"
                  data-testid="input-display-name"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  {t("profile.current_password")}
                </label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  autoComplete="current-password"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/50"
                  data-testid="input-current-password"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  {t("profile.new_password")}{" "}
                  <span className="font-normal text-muted-foreground text-xs">
                    {t("profile.new_password_hint")}
                  </span>
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/50"
                  data-testid="input-new-password"
                />
              </div>
              {saveMessage && (
                <div
                  className={cn(
                    "flex items-center gap-2 text-sm px-3 py-2 rounded-lg",
                    saveMessage.type === "success"
                      ? "bg-green-500/10 text-green-600 dark:text-green-400"
                      : "bg-destructive/10 text-destructive"
                  )}
                  data-testid="save-message"
                >
                  {saveMessage.type === "success" ? (
                    <CheckCircle className="w-4 h-4 shrink-0" />
                  ) : (
                    <AlertCircle className="w-4 h-4 shrink-0" />
                  )}
                  {saveMessage.text}
                </div>
              )}
              <button
                type="submit"
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                data-testid="button-save-profile"
              >
                {saving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {t("profile.saving")}
                  </>
                ) : (
                  t("profile.save")
                )}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
