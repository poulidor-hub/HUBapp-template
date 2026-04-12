import React, { useState, useEffect } from 'react'
import { MoonStar, ShieldCheck, SunMedium } from 'lucide-react'
import { useConfig } from '../context/ConfigContext'
import { useAuth } from '../context/AuthContext'

function Header({ theme, toggleTheme }) {
  const config = useConfig()
  const { isAuthenticated, login, logout } = useAuth()
  const [hubStatus, setHubStatus] = useState({ online: false, checking: true })

  useEffect(() => {
    if (!config.apiUrl) return

    let isActive = true
    const timeoutSignal = () => (
      typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function'
        ? AbortSignal.timeout(3000)
        : undefined
    )

    const checkHubStatus = async (markChecking = false) => {
      if (markChecking) {
        setHubStatus(prev => ({ ...prev, checking: true }))
      }

      try {
        const response = await fetch(`${config.apiUrl}/api/health/detailed`, {
          method: 'GET',
          signal: timeoutSignal()
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const data = await response.json()
        if (!isActive) return

        setHubStatus({
          online: Boolean(data?.hub?.can_authenticate || data?.hub?.connected),
          checking: false
        })
      } catch {
        if (!isActive) return
        setHubStatus({ online: false, checking: false })
      }
    }

    checkHubStatus(true)
    const intervalId = window.setInterval(() => checkHubStatus(false), 15000)

    return () => {
      isActive = false
      window.clearInterval(intervalId)
    }
  }, [config.apiUrl])

  return (
    <header>
      <h1 className="inline-flex items-center gap-2">
        <ShieldCheck className="h-5 w-5" aria-hidden="true" />
        <span>Template App - Hub Auth</span>
      </h1>
      <div className="header-actions">
        <div className="status-indicator">
          <span className={`status-dot ${hubStatus.checking ? '' : hubStatus.online ? 'online' : 'offline'}`} />
          <span>{hubStatus.checking ? 'Vérification...' : hubStatus.online ? 'Hub connecté' : 'Hub indisponible'}</span>
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
