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
    watch: {
      // Docker Desktop on Windows doesn't propagate native filesystem
      // change events through a bind mount to the container's inotify —
      // without polling, chokidar (Vite's watcher) silently never fires and
      // HMR/hot-reload does nothing after the container starts, even though
      // files on the host are saved correctly. Harmless on Linux/macOS.
      usePolling: true,
      interval: 300,
    },
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
