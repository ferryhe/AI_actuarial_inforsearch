import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

const buildValue = (name: string, pattern: RegExp) => {
  const value = process.env[name] || "unknown";
  return pattern.test(value) ? value : "unknown";
};

export default defineConfig({
  define: {
    __BUILD_INFO__: JSON.stringify({
      release_manifest_id: buildValue("BUILD_RELEASE_ID", /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/),
      git_sha: buildValue("BUILD_GIT_SHA", /^[a-fA-F0-9]{7,40}$/),
      build_utc: buildValue("BUILD_UTC", /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/),
    }),
  },
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "client", "src"),
    },
  },
  root: path.resolve(import.meta.dirname, "client"),
  build: {
    outDir: path.resolve(import.meta.dirname, "dist/public"),
    emptyOutDir: true,
  },
  server: {
    host: "0.0.0.0",
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
