import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import type { IncomingMessage } from "node:http";

// A proxy prefix that is ALSO a client-side SPA route (e.g. /chat, /analytics)
// must let browser navigations through to index.html. Without this, reloading
// such a route sends GET <route> to the backend, which has no matching GET
// handler and returns 405 Method Not Allowed. API calls (fetch/XHR) send
// Accept: */* or application/json, so they keep proxying normally.
function spaNavFallback(req: IncomingMessage): string | undefined {
  return req.headers.accept?.includes("text/html") ? "/index.html" : undefined;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiUrl      = env.VITE_API_URL       || "http://localhost:8000";
  // Per-service overrides — set in .env.local when running without full gateway stack
  const authUrl     = env.VITE_AUTH_URL     || apiUrl;
  const predictUrl  = env.VITE_PREDICT_URL  || apiUrl;
  const orchestratorUrl = env.VITE_ORCHESTRATOR_URL || apiUrl;
  const ragUrl      = env.VITE_RAG_URL      || apiUrl;
  const analyticsUrl = env.VITE_ANALYTICS_URL || apiUrl;

  return {
    plugins: [react()],
    resolve: {
      alias: [{ find: "@", replacement: path.resolve(__dirname, "./src") }],
    },
    server: {
      // Proxy API routes to the gateway so the browser avoids CORS in dev.
      // Only used when VITE_API_URL is a relative path or empty.
      proxy: {
        "/auth":          { target: authUrl,    changeOrigin: true },
        "/predict":       { target: predictUrl, changeOrigin: true },
        "/orchestrate":   { target: orchestratorUrl, changeOrigin: true },
        "/query":         { target: ragUrl,     changeOrigin: true },
        "/chat":          { target: ragUrl,     changeOrigin: true, bypass: spaNavFallback },
        "/chat-history":  { target: ragUrl,     changeOrigin: true },
        "/chat-session":  { target: ragUrl,     changeOrigin: true },
        "/feedback":      { target: ragUrl,     changeOrigin: true },
        "/diseases":      { target: apiUrl, changeOrigin: true },
        "/health":        { target: apiUrl, changeOrigin: true },
        "/ingest":        { target: apiUrl, changeOrigin: true },
        "/api/services":  { target: apiUrl, changeOrigin: true },
        "/api/admin":     { target: apiUrl, changeOrigin: true },
        "/api/expert":    { target: apiUrl, changeOrigin: true },
        "/analytics":     { target: analyticsUrl, changeOrigin: true, bypass: spaNavFallback },
        "/ws": {
          target:       apiUrl.replace(/^http/, "ws"),
          changeOrigin: true,
          ws:           true,
        },
      },
    },
  };
});
