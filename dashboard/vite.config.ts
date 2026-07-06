import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Point this at your PayMesh node (facilitator + registry + ledger).
// Override with: VITE_NODE_URL=http://your-host:8001 npm run dev
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
