import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";

interface BuildIdentity {
  release_manifest_id: string;
  git_sha: string;
  build_utc?: string;
}
declare const __BUILD_INFO__: BuildIdentity;
const frontendBuild = typeof __BUILD_INFO__ === "undefined"
  ? { release_manifest_id: "unknown", git_sha: "unknown" }
  : __BUILD_INFO__;

export function BuildInfo({ frontend = frontendBuild }: { frontend?: BuildIdentity }) {
  const { permissions } = useAuth();
  const { t } = useTranslation();
  const allowed = permissions.includes("logs.system.read");
  const [backend, setBackend] = useState<BuildIdentity | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!allowed) return;
    const controller = new AbortController();
    apiGet<{ build_info?: BuildIdentity }>("/api/health", { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) { setBackend(result.build_info ?? null); setFailed(!result.build_info); } })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [allowed]);
  if (!allowed) return null;
  const unavailable = failed || frontend.release_manifest_id === "unknown" || backend?.release_manifest_id === "unknown";
  const mismatch = !!backend && frontend.release_manifest_id !== backend.release_manifest_id;
  return <div className="rounded-lg border border-border p-4 text-sm space-y-1" data-testid="build-info">
    <p>{t("settings.build_frontend")}: <code data-testid="frontend-release">{frontend.release_manifest_id}</code> ({frontend.git_sha.slice(0, 7)})</p>
    <p>{t("settings.build_api")}: <code data-testid="api-release">{backend?.release_manifest_id ?? "—"}</code> ({backend?.git_sha?.slice(0, 7) ?? "—"})</p>
    {(backend || failed) && <p role={unavailable || mismatch ? "alert" : undefined} className={unavailable || mismatch ? "text-amber-600" : "text-muted-foreground"}>
      {t(unavailable ? "settings.build_unavailable" : mismatch ? "settings.build_mismatch" : "settings.build_match")}
    </p>}
  </div>;
}
