import { User } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

function UserCard() {
  const { user, getAppRole } = useAuth()

  if (!user) return null

  const appRole = getAppRole() || 'aucun'
  const tokenType = user.type || 'user'

  return (
    <div className="card">
      <h2><User className="hub-icon" aria-hidden="true" /> Utilisateur connecté</h2>
      <div className="user-info">
        <div className="user-info-item">
          <label>Nom d'utilisateur</label>
          <div className="value">{user.sub || '-'}</div>
        </div>
        <div className="user-info-item">
          <label>Rôle sur cette app</label>
          <div className="value">
            <span className={`role-badge role-${appRole}`}>{appRole}</span>
          </div>
        </div>
        <div className="user-info-item">
          <label>Type de token</label>
          <div className="value">{tokenType}</div>
        </div>
      </div>
    </div>
  )
}

export default UserCard
