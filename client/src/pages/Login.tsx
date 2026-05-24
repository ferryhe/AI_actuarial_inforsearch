import { useState, type FormEvent } from "react";
import { useLocation, Link } from "wouter";
import { apiPost, ApiError, setStoredAuthToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/hooks/use-i18n";
import { BookOpen, Clipboard, Eye, EyeOff, Home } from "lucide-react";

type LoginMode = "email" | "token";

export default function Login() {
  const [, navigate] = useLocation();
  const { refresh } = useAuth();
  const { t, toggleLang } = useI18n();
  const [mode, setMode] = useState<LoginMode>("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleEmailSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!email || !password) {
      setError(t("auth.error.email_password_required"));
      return;
    }
    setLoading(true);
    try {
      await apiPost("/api/auth/login", { email, password });
      setStoredAuthToken("", true);
      await refresh();
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail || err.message);
      } else {
        setError(t("auth.error.login_failed"));
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleTokenSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!token.trim()) {
      setError(t("auth.error.token_required"));
      return;
    }
    setLoading(true);
    try {
      await apiPost("/api/auth/login", { token: token.trim() });
      setStoredAuthToken(token.trim(), false);
      await refresh();
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail || err.message);
      } else {
        setError(t("auth.error.token_login_failed"));
      }
    } finally {
      setLoading(false);
    }
  }

  async function pasteToken() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setToken(text.trim());
    } catch {
      setError(t("auth.error.clipboard_denied"));
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
          <h1 className="text-2xl font-bold tracking-tight">{t("login.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("nav.brand")}</p>
        </div>

        <div className="flex rounded-lg border border-input bg-muted/40 p-1 mb-5 text-sm font-medium gap-1">
          <button
            type="button"
            onClick={() => { setMode("email"); setError(""); }}
            className={`flex-1 rounded-md py-1.5 transition-colors ${mode === "email" ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground"}`}
          >
            {t("login.email_tab")}
          </button>
          <button
            type="button"
            onClick={() => { setMode("token"); setError(""); }}
            className={`flex-1 rounded-md py-1.5 transition-colors ${mode === "token" ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground"}`}
          >
            {t("login.token_tab")}
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive mb-4">
            {error}
          </div>
        )}

        {mode === "email" ? (
          <form onSubmit={handleEmailSubmit} className="space-y-4">
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
                {t("auth.password")}
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
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
              {loading ? t("login.submitting") : t("auth.signIn")}
            </button>
          </form>
        ) : (
          <form onSubmit={handleTokenSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="api-token" className="text-sm font-medium">
                {t("auth.api_token")}
              </label>
              <div className="flex gap-1.5">
                <input
                  id="api-token"
                  type={showToken ? "text" : "password"}
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                  placeholder="Bearer token"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowToken((v) => !v)}
                  className="p-2 rounded-lg border border-input hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                  title={showToken ? t("auth.hide") : t("auth.show")}
                >
                  {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
                {typeof navigator !== "undefined" && navigator.clipboard && (
                  <button
                    type="button"
                    onClick={pasteToken}
                    className="p-2 rounded-lg border border-input hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    title={t("auth.paste")}
                  >
                    <Clipboard className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 active:scale-[0.98] transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? t("login.submitting") : t("login.token_submit")}
            </button>

            <p className="text-xs text-muted-foreground">
              {t("login.token_hint")}
            </p>
          </form>
        )}

        <p className="mt-6 text-center text-sm text-muted-foreground">
          {t("login.no_account")} {" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            {t("auth.register")}
          </Link>
        </p>
      </div>
    </div>
  );
}
