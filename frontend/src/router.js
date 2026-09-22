import { createRouter, createRootRoute, createRoute } from '@tanstack/react-router'
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

const notFoundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '$',
  component: NotFoundPage,
})

const routeTree = rootRoute.addChildren(
  [indexRoute, demoFormRoute, notFoundRoute].filter(Boolean)
)

export const router = createRouter({ routeTree })
