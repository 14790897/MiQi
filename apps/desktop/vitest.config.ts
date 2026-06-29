import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Only run unit tests (not Playwright specs, not real E2E in CI)
    include: [
      'src/**/*.test.ts',
      'tests/**/*.test.ts',
    ],
    exclude: [
      '**/node_modules/**',
      'tests/smoke/**',     // Playwright + real E2E tests
      '**/*.spec.ts',       // Playwright specs
    ],
  },
});
