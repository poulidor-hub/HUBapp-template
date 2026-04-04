import React from 'react'
import { useAuth } from '../context/AuthContext'
import { AlertCircle, AlertTriangle, Info, X, Clock, ExternalLink } from 'lucide-react'

/**
 * Panneau de notifications flottant (position: fixed) en haut à droite.
 * Identique quelle que soit l'application et son frontend.
 * Affiche automatiquement les messages SSE actifs (non-fermés).
 * L'utilisateur doit fermer chaque message manuellement.
 */
export default function MessageBanner() {
  const { activeMessages, dismissMessage, dismissAllMessages, isAuthenticated } = useAuth()

  if (!isAuthenticated || !activeMessages || activeMessages.length === 0) return null

  const getPriorityConfig = (priority) => {
    switch (priority) {
      case 'urgent':
        return {
          className: 'message-banner-item urgent',
          icon: <AlertCircle className="message-banner-icon-svg" />,
        }
      case 'warning':
        return {
          className: 'message-banner-item warning',
          icon: <AlertTriangle className="message-banner-icon-svg" />,
        }
      default:
        return {
          className: 'message-banner-item normal',
          icon: <Info className="message-banner-icon-svg" />,
        }
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
            {activeMessages.length} notification{activeMessages.length > 1 ? 's' : ''}
          </span>
          <button
            className="message-banner-dismiss-all"
            onClick={dismissAllMessages}
            title="Fermer toutes les notifications"
          >
            Tout fermer
            <X className="message-banner-dismiss-all-icon" />
          </button>
        </div>
      )}
      {activeMessages.map((m) => {
        const config = getPriorityConfig(m.priority)
        return (
          <div key={m.id} className={config.className}>
            <div className="message-banner-icon">
              {config.icon}
            </div>
            <div className="message-banner-content">
              <div className="message-banner-header">
                <strong className="message-banner-title">{m.title}</strong>
                <button
                  className="message-banner-close"
                  onClick={() => dismissMessage(m.id)}
                  title="Fermer ce message"
                >
                  <X className="message-banner-close-icon" />
                </button>
              </div>
              {m.body && (
                <p className="message-banner-body">{m.body}</p>
              )}
              {m.action_url && (
                <div className="message-banner-action-wrapper">
                  <a
                    href={m.action_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="message-banner-action"
                  >
                    {m.action_label || 'Consulter'}
                    <ExternalLink className="message-banner-action-icon" />
                  </a>
                </div>
              )}
              <div className="message-banner-meta">
                {(m.sender_app_slug || m.sender_type) && (
                  <span className="message-banner-sender">
                    <span className="message-banner-sender-dot"></span>
                    {m.sender_app_slug || m.sender_type}
                  </span>
                )}
                {m.created_at && (
                  <span className="message-banner-time">
                    <Clock className="message-banner-time-icon" />
                    {formatTime(m.created_at)}
                  </span>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
