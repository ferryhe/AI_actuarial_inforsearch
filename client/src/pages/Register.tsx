import { useState, type FormEvent } from "react";
import { useLocation, Link } from "wouter";
import { apiPost, ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/hooks/use-i18n";
import { BookOpen, Home } from "lucide-react";

function formatAuthSubmitError(err: unknown, t: (key: string) => string, fallbackKey: string): string {
  if (err instanceof ApiError) {
    if (err.status === 429) return t("auth.error.rate_limited");
    if (err.status >= 500) return t("auth.error.system_unavailable");
    return typeof err.detail === "string" && err.detail ? err.detail : err.message;
  }
  return t(fallbackKey);
}

export default function Register() {
  const [, navigate] = useLocation();
  const { refresh } = useAuth();
  const { t, toggleLang } = useI18n();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!email || !password) {
      setError(t("auth.error.email_password_required"));
      return;
    }
    if (password.length < 8) {
      setError(t("register.error.password_min"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("register.error.password_mismatch"));
      return;
    }
    setLoading(true);
    try {
      await apiPost("/api/auth/register", { email, password, display_name: displayName });
      await refresh();
      navigate("/");
    } catch (err) {
      setError(formatAuthSubmitError(err, t, "register.error.failed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-between text-sm">
          <Link href="/" className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground">
            <Home className="w-4 h-4" />
            {t("auth.back_home")}
          </Link>
          <button type="button" onClick={toggleLang} className="text-muted-foreground hover:text-foreground">
            {t("lang.toggle")}
          </button>
        </div>

        <div className="flex flex-col items-center gap-2 mb-8">
          <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
            <BookOpen className="w-5 h-5 text-primary-foreground" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{t("register.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("nav.brand")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label htmlFor="display_name" className="text-sm font-medium">
              {t("register.display_name")} <span className="text-muted-foreground font-normal">{t("register.optional")}</span>
            </label>
            <input
              id="display_name"
              type="text"
              autoComplete="name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              placeholder={t("register.name_placeholder")}
              maxLength={100}
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="email" className="text-sm font-medium">
              {t("auth.email")}
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              placeholder="you@example.com"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="password" className="text-sm font-medium">
              {t("auth.password")} <span className="text-muted-foreground font-normal">{t("register.password_min_hint")}</span>
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              placeholder="••••••••"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="confirm_password" className="text-sm font-medium">
              {t("register.confirm_password")}
            </label>
            <input
              id="confirm_password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              placeholder="••••••••"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 active:scale-[0.98] transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? t("register.submitting") : t("register.submit")}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          {t("register.have_account")} {" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            {t("auth.signIn")}
          </Link>
        </p>
      </div>
    </div>
  );
}
