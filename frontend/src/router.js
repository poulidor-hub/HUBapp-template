// SPDX-License-Identifier: MIT
// Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

import { createRouter, createRootRoute, createRoute, redirect } from '@tanstack/react-router'
import { RootLayout } from './routes/root'
import HomePage from './routes/index'
import NotFoundPage from './routes/notFound'
import DemoFormRoute from './routes/demo/form'

const rootRoute = createRootRoute({
  component: RootLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: HomePage,
})

// Route de démonstration : DEV uniquement. En production, la route n'est
// pas déclarée → /demo/form retombe sur le splat 404 (pas de démo exposée).
const demoFormRoute = import.meta.env.DEV
  ? createRoute({
      getParentRoute: () => rootRoute,
      path: '/demo/form',
      component: DemoFormRoute,
    })
  : null

// Retour SSO du Hub : le dashboard ouvre {frontend_url}/callback?access_token=...
// Le token est consommé de façon synchrone par AuthContext (monté au-dessus du
// routeur) ; cette route absorbe le path pour ne pas tomber dans le splat 404.
const callbackRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/callback',
  beforeLoad: () => {
    throw redirect({ to: '/', replace: true })
  },
})

const notFoundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '$',
  component: NotFoundPage,
})

const routeTree = rootRoute.addChildren(
  [indexRoute, demoFormRoute, callbackRoute, notFoundRoute].filter(Boolean)
)

export const router = createRouter({ routeTree })
