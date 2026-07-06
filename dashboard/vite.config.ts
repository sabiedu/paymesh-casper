import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Vite dev server proxies API calls to the PayMesh node (:8001),
// so everything is same-origin — no CORS, one public hostname needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // bind to all interfaces (e.g. when exposing the dev server remotely)
    proxy: {
      "/registry": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/agent": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/recent_payments": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/demo": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        // Let the SPA handle /demo page route; only proxy API sub-paths
        bypass: (req) => {
          if (req.method === "GET" && /^\/demo\/?(\?.*)?$/.test(req.url)) return "/index.html";
        },
      },
      "/serve": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/observe": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        // Let the SPA handle /observe page route; only proxy /observe/metrics
        bypass: (req) => {
          if (req.method === "GET" && /^\/observe\/?(\?.*)?$/.test(req.url)) return "/index.html";
        },
      },
      "/health": { target: "http://127.0.0.1:8001", changeOrigin: true },
    },
  },
});
