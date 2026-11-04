// SPDX-License-Identifier: MIT
// Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

import FormDemo from '../../components/demo/FormDemo'
import PageHeader from '../../components/PageHeader'
import { FormDevtoolsPanel } from '@tanstack/react-form-devtools'

export default function FormDemoPage() {
  return (
    <>
      <PageHeader
        title="Démo TanStack Form"
        back={{ onClick: () => window.history.back() }}
      />
      {/* FormDemo rend lui-même le hub-panel hub-panel--padded (migré Task 2) :
          pas de wrapper supplémentaire — règle « pas de carte dans carte ». */}
      <FormDemo />
      {import.meta.env.DEV && <FormDevtoolsPanel position="bottom-left" />}
    </>
  )
}
