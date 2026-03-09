import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Users as UsersIcon,
  Shield,
  ShieldCheck,
  UserCheck,
  UserX,
  RotateCcw,
  Loader2,
  RefreshCw,
  X,
  Eye,
  ChevronDown,
  Lock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface User {
  id: number;
  username: string;
  email?: string;
  role: string;
  is_active: boolean;
  quota_used?: number;
  quota_limit?: number;
  created_at?: string;
  last_login?: string;
}

interface ActivityEntry {
  id: number;
  action: string;
  detail?: string;
  timestamp: string;
  ip_address?: string;
}

export default function UsersPage() {
  const { t } = useTranslation();
  const { user: currentUser, isLoading: authLoading } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<Record<number, string>>({});
  const [activityModal, setActivityModal] = useState<{ user: User; entries: ActivityEntry[] } | null>(null);
  const [activityLoading, setActivityLoading] = useState(false);
  const [roleDropdown, setRoleDropdown] = useState<number | null>(null);
  const roleDropdownRef = useRef<HTMLDivElement | null>(null);
  const isAdmin = currentUser?.role === "admin";

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (roleDropdownRef.current && !roleDropdownRef.current.contains(e.target as Node)) {
        setRoleDropdown(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<{ users: User[] } | User[]>("/api/admin/users");
      setUsers(Array.isArray(data) ? data : data.users || []);
    } catch (e: any) {
      setError(e.message || "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleRoleChange = async (userId: number, newRole: string) => {
    setActionLoading((prev) => ({ ...prev, [userId]: "role" }));
    setRoleDropdown(null);
    try {
      await apiPost(`/api/admin/users/${userId}/role`, { role: newRole });
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, role: newRole } : u)));
    } catch (e: any) {
      alert(e.message || "Failed to change role");
    } finally {
      setActionLoading((prev) => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
    }
  };

  const handleToggleActive = async (user: User) => {
    setActionLoading((prev) => ({ ...prev, [user.id]: "toggle" }));
    try {
      const endpoint = user.is_active
        ? `/api/admin/users/${user.id}/disable`
        : `/api/admin/users/${user.id}/enable`;
      await apiPost(endpoint);
      setUsers((prev) =>
        prev.map((u) => (u.id === user.id ? { ...u, is_active: !u.is_active } : u))
      );
    } catch (e: any) {
      alert(e.message || "Failed to toggle user status");
    } finally {
      setActionLoading((prev) => {
        const next = { ...prev };
        delete next[user.id];
        return next;
      });
    }
  };

  const handleResetQuota = async (userId: number) => {
    setActionLoading((prev) => ({ ...prev, [userId]: "quota" }));
    try {
      await apiPost(`/api/admin/users/${userId}/reset-quota`);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, quota_used: 0 } : u))
      );
    } catch (e: any) {
      alert(e.message || "Failed to reset quota");
    } finally {
      setActionLoading((prev) => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
    }
  };

  const handleViewActivity = async (user: User) => {
    setActivityLoading(true);
    setActivityModal({ user, entries: [] });
    try {
      const data = await apiGet<{ activity: ActivityEntry[] } | ActivityEntry[]>(
        `/api/admin/users/${user.id}/activity`
      );
      const entries = Array.isArray(data) ? data : data.activity || [];
      setActivityModal({ user, entries });
    } catch (e: any) {
      setActivityModal({ user, entries: [] });
    } finally {
      setActivityLoading(false);
    }
  };

  const roleOptions = ["admin", "registered", "premium", "operator", "operator_ai"];

  return (
    <div className="space-y-6">
      {/* Access denied message for non-admin users (shown after auth loading completes) */}
      {!authLoading && !isAdmin && (
        <div className="flex flex-col items-center justify-center py-32 gap-4 text-muted-foreground">
          <Lock className="w-10 h-10 opacity-40" />
          <p className="text-lg font-medium">{t("users.admin_only")}</p>
          <p className="text-sm">{t("users.admin_only_desc")}</p>
        </div>
      )}
      {(authLoading || isAdmin) && (<>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" data-testid="text-users-title">
            {t("users.title")}
          </h1>
          <p className="text-muted-foreground text-sm mt-1" data-testid="text-users-subtitle">
            {t("users.subtitle")}
          </p>
        </div>
        <button
          onClick={fetchUsers}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50"
          data-testid="button-refresh-users"
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
          {t("users.refresh")}
        </button>
      </div>

      {error && (
        <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg text-sm" data-testid="text-users-error">
          {error}
        </div>
      )}

      {loading && !users.length ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : users.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground" data-testid="text-no-users">
          <UsersIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>{t("users.no_users")}</p>
        </div>
      ) : (
        <div className="border border-border rounded-lg overflow-hidden bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">{t("users.col_username")}</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">{t("users.col_email")}</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">{t("users.col_role")}</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">{t("users.col_status")}</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">{t("users.col_quota")}</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">{t("users.col_last_login")}</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">{t("users.col_actions")}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <motion.tr
                    key={user.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors"
                    data-testid={`row-user-${user.id}`}
                  >
                    <td className="px-4 py-3 font-medium" data-testid={`text-username-${user.id}`}>
                      {user.username}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground" data-testid={`text-email-${user.id}`}>
                      {user.email || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="relative" ref={roleDropdown === user.id ? roleDropdownRef : undefined}>
                        <button
                          onClick={() => setRoleDropdown(roleDropdown === user.id ? null : user.id)}
                          disabled={!!actionLoading[user.id]}
                          className={cn(
                            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors",
                            user.role === "admin"
                              ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                              : user.role === "premium"
                                ? "bg-violet-500/10 text-violet-600 dark:text-violet-400"
                                : user.role === "operator" || user.role === "operator_ai"
                                  ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                                  : "bg-green-500/10 text-green-600 dark:text-green-400"
                          )}
                          data-testid={`button-role-${user.id}`}
                        >
                          {user.role === "admin" ? (
                            <ShieldCheck className="w-3.5 h-3.5" />
                          ) : (
                            <Shield className="w-3.5 h-3.5" />
                          )}
                          {user.role}
                          <ChevronDown className="w-3 h-3" />
                          {actionLoading[user.id] === "role" && (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          )}
                        </button>
                        {roleDropdown === user.id && (
                          <div className="absolute z-10 mt-1 bg-popover border border-border rounded-md shadow-md py-1 min-w-[100px]">
                            {roleOptions.map((role) => (
                              <button
                                key={role}
                                onClick={() => handleRoleChange(user.id, role)}
                                className={cn(
                                  "block w-full text-left px-3 py-1.5 text-xs hover:bg-muted transition-colors",
                                  role === user.role && "font-bold text-primary"
                                )}
                                data-testid={`button-set-role-${role}-${user.id}`}
                              >
                                {role}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleToggleActive(user)}
                        disabled={!!actionLoading[user.id]}
                        className={cn(
                          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors",
                          user.is_active
                            ? "bg-green-500/10 text-green-600 dark:text-green-400"
                            : "bg-red-500/10 text-red-600 dark:text-red-400"
                        )}
                        data-testid={`button-toggle-active-${user.id}`}
                      >
                        {actionLoading[user.id] === "toggle" ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : user.is_active ? (
                          <UserCheck className="w-3.5 h-3.5" />
                        ) : (
                          <UserX className="w-3.5 h-3.5" />
                        )}
                        {user.is_active ? t("users.active") : t("users.disabled")}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground" data-testid={`text-quota-${user.id}`}>
                      {user.quota_limit != null ? (
                        <span>
                          {user.quota_used ?? 0} / {user.quota_limit}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs" data-testid={`text-last-login-${user.id}`}>
                      {user.last_login
                        ? new Date(user.last_login).toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleViewActivity(user)}
                          className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                          title={t("users.view_activity")}
                          data-testid={`button-activity-${user.id}`}
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        {user.quota_limit != null && (
                          <button
                            onClick={() => handleResetQuota(user.id)}
                            disabled={!!actionLoading[user.id]}
                            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                            title={t("users.reset_quota")}
                            data-testid={`button-reset-quota-${user.id}`}
                          >
                            {actionLoading[user.id] === "quota" ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <RotateCcw className="w-4 h-4" />
                            )}
                          </button>
                        )}
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <AnimatePresence>
        {activityModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
            onClick={() => setActivityModal(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-card border border-border rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col"
              data-testid="modal-user-activity"
            >
              <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
                <h3 className="font-semibold text-base">
                  {t("users.activity_title")} — {activityModal.user.username}
                </h3>
                <button
                  onClick={() => setActivityModal(null)}
                  className="p-1 rounded hover:bg-muted"
                  data-testid="button-close-activity"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-5">
                {activityLoading ? (
                  <div className="flex items-center justify-center py-10">
                    <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                  </div>
                ) : activityModal.entries.length === 0 ? (
                  <p className="text-center text-muted-foreground py-10" data-testid="text-no-activity">
                    {t("users.no_activity")}
                  </p>
                ) : (
                  <div className="space-y-3">
                    {activityModal.entries.map((entry) => (
                      <div
                        key={entry.id}
                        className="flex items-start gap-3 text-sm border-b border-border pb-3 last:border-0"
                        data-testid={`activity-entry-${entry.id}`}
                      >
                        <div className="flex-1 min-w-0">
                          <p className="font-medium">{entry.action}</p>
                          {entry.detail && (
                            <p className="text-muted-foreground text-xs mt-0.5">{entry.detail}</p>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                          <div>{new Date(entry.timestamp).toLocaleString()}</div>
                          {entry.ip_address && <div className="mt-0.5">{entry.ip_address}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      </>)}
    </div>
  );
}
