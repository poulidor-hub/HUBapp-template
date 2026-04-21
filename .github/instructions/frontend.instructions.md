---
description: "Use when editing React components, Vite frontend logic, TanStack Query hooks, or frontend styling. Covers API wrappers, context usage, and theme conventions."
name: "Frontend Guidelines"
applyTo:
  - "frontend/src/**/*.js"
  - "frontend/src/**/*.jsx"
---

# Frontend Guidelines

- Keep API access centralized through [frontend/src/hooks/useApiQuery.js](../../frontend/src/hooks/useApiQuery.js) and [frontend/src/hooks/useApiMutation.js](../../frontend/src/hooks/useApiMutation.js). Add a shared hook before introducing repeated `fetch` logic in components.
- Resolve runtime config through [frontend/src/context/ConfigContext.jsx](../../frontend/src/context/ConfigContext.jsx) and authentication state through [frontend/src/context/AuthContext.jsx](../../frontend/src/context/AuthContext.jsx).
- Match the existing component style in [frontend/src/App.jsx](../../frontend/src/App.jsx) and [frontend/src/components](../../frontend/src/components): function components, hooks for local state, and minimal abstraction unless repetition is real.
- Preserve the theme mechanism already in use: `data-theme` on the root element, theme persistence in local storage, and visual tokens in [frontend/src/styles/index.css](../../frontend/src/styles/index.css).
- Keep endpoint paths relative to the configured API base and use [docs/API.md](../../docs/API.md) as the contract reference when UI changes depend on backend behavior.
- Validate non-trivial frontend changes with `cd frontend && npm run build`.