// SPDX-License-Identifier: MIT
// Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'
import { router } from './router'
import { startMockService } from './mocks/browser'
import ErrorBoundary from '@poulidor/hub-socle/components/ErrorBoundary.jsx'
import { ConfigProvider } from '@poulidor/hub-socle/context/ConfigContext.jsx'
import { AuthProvider } from '@poulidor/hub-socle/context/AuthContext.jsx'
import { queryClient } from '@poulidor/hub-socle/lib/queryClient.js'
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
                  <ReactQueryDevtools initialIsOpen={false} position="right" />
                  <TanStackRouterDevtools router={router} position="bottom-left" />
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
