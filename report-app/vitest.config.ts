import { defineConfig } from "vitest/config";

// happy-dom gives the page tests a real DOM; the pure-geometry tests
// simply ignore it.
export default defineConfig({
  test: { environment: "happy-dom" },
});
