import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['test/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'text-summary'],
      include: ['src/**/*.ts'],
      exclude: ['src/rubric/**'],
      thresholds: {
        // Overall floor per CLAUDE.md's engineering standards.
        lines: 80,
        statements: 80,
        functions: 80,
        branches: 75,
        // Per-file floors for the modules that directly produce the CI-gate verdict.
        perFile: true,
        'src/scorer/composite.ts': {
          lines: 95,
          statements: 95,
          functions: 95,
          branches: 90,
        },
        'src/sources/LLMJudgeSource.ts': {
          lines: 95,
          statements: 95,
          functions: 95,
          branches: 90,
        },
      },
    },
  },
});
