import React, { useState, useEffect } from 'react'
import { useConfig } from '../context/ConfigContext'
import { useAuth } from '../context/AuthContext'

function Header({ theme, toggleTheme }) {
  const config = useConfig()
  const { isAuthenticated, login, logout } = useAuth()
  const [hubStatus, setHubStatus] = useState({ online: false, checking: true })

  useEffect(() => {
    checkHubStatus()
  }, [config.hubApiUrl])

  const checkHubStatus = async () => {
    try {
      const response = await fetch(`${config.hubApiUrl}/api/auth/public-key`)
      setHubStatus({ online: response.ok, checking: false })
    } catch {
      setHubStatus({ online: false, checking: false })
    }
  }

  return (
    <header>
      <h1>🔐 Template App - Hub Auth</h1>
      <div className="header-actions">
        <div className="status-indicator">
          <span className={`status-dot ${hubStatus.checking ? '' : hubStatus.online ? 'online' : 'offline'}`} />
          <span>{hubStatus.checking ? 'Vérification...' : hubStatus.online ? 'Hub connecté' : 'Hub indisponible'}</span>
        </div>
        <button className="theme-toggle" onClick={toggleTheme} title="Changer le thème">
          🌓
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
