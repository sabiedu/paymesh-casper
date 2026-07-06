import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Vite dev server proxies API calls to the PayMesh node (:8001),
// so everything is same-origin — no CORS, one public hostname needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // bind to all interfaces (needed for cloudflared tunnel)
    allowedHosts: ["paymesh.sabiedu.online", ".sabiedu.online"],
    proxy: {
      "/registry": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/agent": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/recent_payments": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/demo": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/serve": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8001", changeOrigin: true },
    },
  },
});
