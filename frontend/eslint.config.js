import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'

/**
 * ESLint (flat config) — filet qualité du frontend du template.
 *
 * - rules-of-hooks : ERREUR (violations de contrat React)
 * - exhaustive-deps : WARNING (attrape les deps manquantes de useEffect —
 *   source classique d'états semi-auth ou de listeners fantômes)
 *
 * `npm run lint` — lance aussi `npm run lint:classes` pour le CSS (CASCADE).
 */
export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'public/**', 'scripts/**', 'mockServiceWorker.js'],
  },
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: { ...globals.browser },
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      'react-hooks': reactHooks,
    },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
]
