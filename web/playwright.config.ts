import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  // Reduced motion turns autoplay off, so pixels are taken at a known hour.
  use: { baseURL: "http://localhost:4321", viewport: { width: 1000, height: 700 }, reducedMotion: "reduce", timezoneId: "UTC" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1000, height: 700 } } }],
  webServer: {
    command: "npm run build && npm run preview",
    url: "http://localhost:4321/wave-map",
    reuseExistingServer: true,
    timeout: 180_000,
  },
});
