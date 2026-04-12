import React from 'react'
import { MoonStar, ShieldCheck, SunMedium } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useApiQuery } from '../hooks/useApiQuery'

function Header({ theme, toggleTheme }) {
  const { isAuthenticated, login, logout } = useAuth()

  const { data, isLoading: checking } = useApiQuery({
    queryKey: ['hub-status'],
    endpoint: '/api/health/detailed',
    refetchInterval: 15000,
    retry: false,
    staleTime: 10_000,
  })

  const online = Boolean(data?.hub?.can_authenticate || data?.hub?.connected)

  return (
    <header>
      <h1 className="inline-flex items-center gap-2">
        <ShieldCheck className="h-5 w-5" aria-hidden="true" />
        <span>Template App - Hub Auth</span>
      </h1>
      <div className="header-actions">
        <div className="status-indicator">
          <span className={`status-dot ${checking ? '' : online ? 'online' : 'offline'}`} />
          <span>{checking ? 'Vérification...' : online ? 'Hub connecté' : 'Hub indisponible'}</span>
        </div>
        <button
          className="theme-toggle inline-flex items-center justify-center"
          onClick={toggleTheme}
          title="Changer le thème"
          aria-label="Changer le thème"
        >
          {theme === 'dark' ? (
            <SunMedium className="h-5 w-5" aria-hidden="true" />
          ) : (
            <MoonStar className="h-5 w-5" aria-hidden="true" />
          )}
        </button>
        {isAuthenticated ? (
          <button className="btn btn-danger btn-small" onClick={logout}>
            Déconnexion
          </button>
        ) : (
          <button className="btn btn-primary btn-small" onClick={login}>
            Connexion
          </button>
        )}
      </div>
    </header>
  )
}

export default Header
