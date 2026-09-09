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
    // Required so @testing-library/react's automatic afterEach(cleanup)
    // registers — without it, DOM from one test leaks into the next.
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.tsx"],
    css: false,
  },
});
