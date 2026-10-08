import { User } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

// Mapping rôle → variante hub-badge (spec §4.3) : admin = pill, user = défaut,
// viewer = success, manager = warning (couleur héritée de l'ancien .role-manager).
const roleBadgeClasses = (role) => {
  switch (role) {
    case 'admin': return 'hub-badge hub-badge--pill'
    case 'viewer': return 'hub-badge hub-badge-success'
    case 'manager': return 'hub-badge hub-badge-warning'
    default: return 'hub-badge'
  }
}

function UserCard() {
  const { user, getAppRole } = useAuth()

  if (!user) return null

  const appRole = getAppRole() || 'aucun'
  const tokenType = user.type || 'user'

  return (
    <div className="hub-panel hub-panel--padded">
      <h2><User className="hub-icon" aria-hidden="true" /> Utilisateur connecté</h2>
      <div className="user-info">
        <div className="user-info-item">
          <label>Nom d'utilisateur</label>
          <div className="value">{user.sub || '-'}</div>
        </div>
        <div className="user-info-item">
          <label>Rôle sur cette app</label>
          <div className="value">
            <span className={roleBadgeClasses(appRole)}>{appRole}</span>
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
