// SPDX-License-Identifier: MIT
// Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

export async function startMockService() {
  if (!import.meta.env.DEV) return

  const worker = setupWorker(...handlers)

  await worker.start({
    onUnhandledRequest: 'bypass',
    quiet: false,
  })

  console.log('[MSW] ✅ Mocking enabled')
}
