// SPDX-License-Identifier: MIT
// Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

import { useState, useEffect } from 'react'
import { Outlet } from '@tanstack/react-router'
import { useConfig } from '@poulidor/hub-socle/context/ConfigContext.jsx'
import { useAuth } from '@poulidor/hub-socle/context/AuthContext.jsx'
import Header from '@poulidor/hub-socle/components/Header.jsx'
import MessageBanner from '@poulidor/hub-socle/components/MessageBanner.jsx'
import MessageArchive from '@poulidor/hub-socle/components/MessageArchive.jsx'

export function RootLayout() {
  const [theme, setTheme] = useState(() =>
    localStorage.getItem('theme') || 'light'
  )
  const config = useConfig()
  const { isAuthenticated, restoring, ssoChecking } = useAuth()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark')
  }

  if (!config.loaded) {
    return (
      <div className="loading">
        <p>Chargement de la configuration...</p>
      </div>
    )
  }

  // Boot d'authentification en cours (restauration silencieuse du refresh
  // token, ou vérification SSO auprès du Hub) : on ne montre ni l'écran
  // « Se connecter » ni une page vide — un simple état de connexion.
  const authBootstrapping = !isAuthenticated && (restoring || ssoChecking)

  return (
    <div className="app">
      <Header theme={theme} toggleTheme={toggleTheme} />
      <div className="container">
        {authBootstrapping ? (
          <div className="loading">
            <p>Connexion au Hub...</p>
          </div>
        ) : (
          <Outlet />
        )}
      </div>
      {/* Messagerie Hub (SSE) — flottants, null si non authentifié */}
      <MessageBanner />
      <MessageArchive />
    </div>
  )
}
