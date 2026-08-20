import React from 'react'
import { Link } from '@tanstack/react-router'
import { useAuth } from '../context/AuthContext'
import LoginPrompt from '../components/LoginPrompt'

export default function HomePage() {
  const { isAuthenticated, user } = useAuth()

  if (!isAuthenticated) {
    return <LoginPrompt />
  }

  return (
    <>
      <div className="card">
        <h2>Bienvenue {user?.username || user?.sub} !</h2>
        <p>Votre application est prête. Commencez à développer ici.</p>
      </div>
      <div className="card" style={{ marginTop: '1rem' }}>
        <h3>Outils de développement</h3>
        <p>
          <Link to="/demo/form" style={{ color: 'var(--color-primary)' }}>
            → Démo TanStack Form (avec DevTools)
          </Link>
        </p>
      </div>
    </>
  )
}
