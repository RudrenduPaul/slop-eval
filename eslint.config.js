const tseslint = require('@typescript-eslint/eslint-plugin');
const tsParser = require('@typescript-eslint/parser');

const nodeGlobals = {
  process: 'readonly',
  console: 'readonly',
  require: 'readonly',
  module: 'writable',
  __dirname: 'readonly',
  __filename: 'readonly',
  Buffer: 'readonly',
  fetch: 'readonly',
  setTimeout: 'readonly',
};

module.exports = [
  {
    ignores: ['dist/**', 'node_modules/**', '.slop-eval-cache/**', 'coverage/**'],
  },
  {
    files: ['src/**/*.ts', 'test/**/*.ts'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        sourceType: 'module',
      },
      globals: nodeGlobals,
    },
    plugins: {
      '@typescript-eslint': tseslint,
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      'no-console': 'warn',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['*.js', '*.cjs'],
    languageOptions: {
      sourceType: 'commonjs',
      globals: nodeGlobals,
    },
  },
];
