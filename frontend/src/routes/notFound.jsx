import React from 'react'
import { Link } from '@tanstack/react-router'

export default function NotFoundPage() {
  return (
    <div className="card">
      <h2>404 — Page introuvable</h2>
      <p>La page demandée n'existe pas.</p>
      <Link to="/" style={{ color: 'var(--accent)' }}>
        ← Retour à l'accueil
      </Link>
    </div>
  )
}
