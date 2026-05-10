import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Reference-only directories — design handoff, generated docs, conversation archives.
  // None of these are loaded by Vite or the running app.
  globalIgnores(['dist', 'project/**', 'chats/**', 'docs/**', 'backend/**']),

  // Vite/Node config files run in Node — use Node globals (process, __dirname, etc.)
  {
    files: ['vite.config.{js,ts}', '*.config.{js,ts}'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },

  // Source application
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // HMR-only — does not affect production. We legitimately co-locate
      // small constants/utilities with components in this app.
      'react-refresh/only-export-components': 'off',

      // react-hooks v7 experimental strict rules — fire on legitimate React
      // patterns (refs read in event handlers, deterministic-by-key useMemo,
      // setState-in-effect for derived data). Keep as warnings so genuine
      // issues still surface, but don't block the build on shape-only flags.
      'react-hooks/refs': 'warn',
      'react-hooks/purity': 'warn',
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/static-components': 'warn',
    },
  },
])
