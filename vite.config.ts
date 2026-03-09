import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
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
      "/email-login": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/login": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        bypass(req: { method?: string }) {
          // Only proxy POST (token login API call); GET navigates to React SPA
          if (req.method !== "POST") return "/index.html";
        },
      },
      "/register": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/logout": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
