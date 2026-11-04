// SPDX-License-Identifier: MIT
// Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

import { useAuth } from '@poulidor/hub-socle/context/AuthContext.jsx'
import LoginPrompt from '@poulidor/hub-socle/components/LoginPrompt.jsx'
import ExampleList from '../components/ExampleList'

// Accueil : la barre app (Header du socle) porte déjà le titre, la version
// et l'état Hub — pas de PageHeader ici (un seul en-tête, un seul h1).
// Les pages de détail/formulaires gardent leur PageHeader canonique.
export default function HomePage() {
  const { isAuthenticated } = useAuth()

  if (!isAuthenticated) {
    return <LoginPrompt />
  }

  return <ExampleList />
}
