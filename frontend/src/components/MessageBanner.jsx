import React from 'react'
import { useAuth } from '../context/AuthContext'

/**
 * Bandeau flottant (position: fixed) en haut de l'écran.
 * Identique quelle que soit l'application et son frontend.
 * Affiche automatiquement les messages SSE actifs (non-fermés).
 * L'utilisateur doit fermer chaque message manuellement.
 */
export default function MessageBanner() {
  const { activeMessages, dismissMessage, dismissAllMessages, isAuthenticated } = useAuth()

  if (!isAuthenticated || !activeMessages || activeMessages.length === 0) return null

  const getPriorityClass = (priority) => {
    switch (priority) {
      case 'urgent': return 'message-banner-item urgent'
      case 'warning': return 'message-banner-item warning'
      default: return 'message-banner-item normal'
    }
  }

  const getPriorityIcon = (priority) => {
    switch (priority) {
      case 'urgent': return '🔴'
      case 'warning': return '🟡'
      default: return '🔵'
    }
  }

  const formatTime = (dateStr) => {
    if (!dateStr) return ''
    return new Date(dateStr).toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
    })
  }

  return (
    <div className="message-banner">
      {activeMessages.length > 1 && (
        <div className="message-banner-controls">
          <span className="message-banner-count">
            {activeMessages.length} message{activeMessages.length > 1 ? 's' : ''}
          </span>
          <button
            className="message-banner-dismiss-all"
            onClick={dismissAllMessages}
            title="Tout fermer"
          >
            Tout fermer ✕
          </button>
        </div>
      )}
      {activeMessages.map((m, idx) => (
        <div key={m.id || idx} className={getPriorityClass(m.priority)}>
          <span className="message-banner-icon">{getPriorityIcon(m.priority)}</span>
          <div className="message-banner-content">
            <strong className="message-banner-title">{m.title}</strong>
            {m.body && <span className="message-banner-body">{m.body}</span>}
          </div>
          <div className="message-banner-meta">
            <span className="message-banner-sender">
              {m.sender_app_slug || m.sender_type}
            </span>
            <span className="message-banner-time">{formatTime(m.created_at)}</span>
          </div>
          {m.action_url && (
            <a
              href={m.action_url}
              target="_blank"
              rel="noopener noreferrer"
              className="message-banner-action"
            >
              {m.action_label || 'Ouvrir'}
            </a>
          )}
          <button
            className="message-banner-close"
            onClick={() => dismissMessage(m.id)}
            title="Fermer ce message"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
