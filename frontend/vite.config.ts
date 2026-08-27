import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker, the API lives on the "api" service hostname; locally (npm run
// dev outside Docker) it's on localhost. Override with VITE_API_PROXY_TARGET.
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
