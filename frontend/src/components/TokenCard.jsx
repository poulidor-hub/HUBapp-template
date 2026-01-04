import React from 'react'
import { useAuth } from '../context/AuthContext'

function TokenCard() {
  const { user, token } = useAuth()

  if (!user) return null

  const copyToken = () => {
    if (token) {
      navigator.clipboard.writeText(token)
      alert('Token copié !')
    }
  }

  return (
    <div className="card">
      <div className="token-header">
        <h2>🎟️ Token JWT</h2>
        <button className="btn btn-small btn-secondary" onClick={copyToken}>
          Copier
        </button>
      </div>
      <div className="token-display">
        {JSON.stringify(user, null, 2)}
      </div>
    </div>
  )
}

export default TokenCard
