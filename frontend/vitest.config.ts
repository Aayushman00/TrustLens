import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Separate from vite.config.ts (the dev/build config) so `vitest` never
// pulls test-only deps (jsdom, testing-library) into the app build. Only
// covers component/DOM tests (*.test.tsx); src/lib/format.test.ts keeps
// running under node:test via `npm test`'s first step (see package.json).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // Each worker boots its own jsdom; at the default (about one per CPU) the
    // workers oversubscribe the machine and the heavy wizard flow test took
    // 0.8-5.1s instead of ~0.3s (5s test timeout). Measured on 24 logical
    // CPUs: 4-8 workers finish the suite in 15-17s vs 39s at the default.
    maxWorkers: 6,
    // Required so @testing-library/react's automatic afterEach(cleanup)
    // registers — without it, DOM from one test leaks into the next.
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.tsx", "src/ds/**/*.test.ts"],
    css: false,
  },
});
