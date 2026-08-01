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

const demoFormRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/demo/form',
  component: DemoFormRoute,
})

const notFoundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '$',
  component: NotFoundPage,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  demoFormRoute,
  notFoundRoute,
])

export const router = createRouter({ routeTree })
