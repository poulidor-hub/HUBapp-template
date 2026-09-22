import { MoonStar, ShieldCheck, SunMedium } from 'lucide-react'
import { APP_VERSION } from '../config'
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
      <div className="header-title-group">
        <h1 className="app-title">
          <ShieldCheck className="hub-icon" aria-hidden="true" />
          <span>Template App - Hub Auth</span>
        </h1>
        <span className="header-version">v{APP_VERSION}</span>
      </div>
      <div className="header-actions">
        <div className="status-indicator">
          <span className={`status-dot ${checking ? '' : online ? 'online' : 'offline'}`} />
          <span>{checking ? 'Vérification...' : online ? 'Hub connecté' : 'Hub indisponible'}</span>
        </div>
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          title="Changer le thème"
          aria-label="Changer le thème"
        >
          {theme === 'dark' ? (
            <SunMedium className="hub-icon" aria-hidden="true" />
          ) : (
            <MoonStar className="hub-icon" aria-hidden="true" />
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
