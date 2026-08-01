import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'
import { router } from './router'
import { startMockService } from './mocks/browser'
import ErrorBoundary from './components/ErrorBoundary'
import { ConfigProvider } from './context/ConfigContext'
import { AuthProvider } from './context/AuthContext'
import { queryClient } from './lib/queryClient'
import './styles/app.css'

async function bootstrap() {
  await startMockService()

  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <ErrorBoundary>
        <ConfigProvider>
          <AuthProvider>
            <QueryClientProvider client={queryClient}>
              <RouterProvider router={router} />
              {import.meta.env.DEV && (
                <>
                  <ReactQueryDevtools initialIsOpen={false} />
                  <TanStackRouterDevtools router={router} position="bottom-right" />
                </>
              )}
            </QueryClientProvider>
          </AuthProvider>
        </ConfigProvider>
      </ErrorBoundary>
    </React.StrictMode>
  )
}

bootstrap()
