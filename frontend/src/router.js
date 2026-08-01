import { createRouter, createRootRoute, createRoute } from '@tanstack/react-router'
import { RootLayout } from './routes/root'
import HomePage from './routes/index'
import NotFoundPage from './routes/notFound'

const rootRoute = createRootRoute({
  component: RootLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: HomePage,
})

const notFoundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '$',
  component: NotFoundPage,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  notFoundRoute,
])

export const router = createRouter({ routeTree })
