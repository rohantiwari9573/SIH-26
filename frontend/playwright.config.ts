import { defineConfig } from "@playwright/test";

// Minimal smoke suite — see e2e/README.md for scope/rationale. Runs against
// an already-running dev server (docker compose's frontend + api services);
// does not start its own server, since the real target is the actual
// containerized stack, not a throwaway build.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.ARGUS_BASE_URL || "http://localhost:5173",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
  },
});
