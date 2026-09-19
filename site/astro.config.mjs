// @ts-check
import { defineConfig } from "astro/config";

// Static output only: the public site never queries a database (REQUIREMENTS.md section 8).
export default defineConfig({
  output: "static",
  // Set SITE_URL in the deploy environment for correct canonical and sitemap URLs.
  site: process.env.SITE_URL || "https://example.invalid",
  trailingSlash: "always",
  build: { format: "directory" },
  // Never inline scripts into HTML, so the Content-Security-Policy can be script-src 'self'
  // (see docker/nginx.conf).
  vite: { build: { assetsInlineLimit: 0 } },
});
