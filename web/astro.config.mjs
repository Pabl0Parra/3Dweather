import { defineConfig } from "astro/config";

export default defineConfig({
  output: "static",
  // Pages as /a/b.html: the publisher drops ".html" from keys, so /a/b is served from R2 without a routing rule.
  build: { format: "file" },
  server: { port: 4321 },
});
