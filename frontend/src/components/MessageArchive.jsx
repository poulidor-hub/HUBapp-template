import React, { useState } from 'react'
import { Check, CheckCheck, Mail, X } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

/**
 * Bouton flottant subtil (bas-droite) + panneau d'archive des messages.
 * Semi-transparent au repos, plus visible au survol.
 * Affiche l'historique complet (lus + non-lus).
 */
export default function MessageArchive() {
  const { unreadMessages, unreadCount, markMessageRead, markAllMessagesRead, isAuthenticated } = useAuth()
  const [isOpen, setIsOpen] = useState(false)

  if (!isAuthenticated) return null

  const togglePanel = () => setIsOpen(prev => !prev)

  const handleMarkRead = async (e, msgId) => {
    e.stopPropagation()
    await markMessageRead(msgId)
  }

  const getPriorityClass = (priority) => {
    switch (priority) {
      case 'urgent': return 'message-archive-msg urgent'
      case 'warning': return 'message-archive-msg warning'
      default: return 'message-archive-msg'
    }
  }

  const formatTime = (dateStr) => {
    if (!dateStr) return ''
    return new Date(dateStr).toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
    })
  }

  return (
    <>
      {/* Bouton flottant subtil */}
      <button
        className={`message-archive-btn ${unreadCount > 0 ? 'has-unread' : ''}`}
        onClick={togglePanel}
        title="Historique des messages"
      >
        <Mail className="hub-icon" aria-hidden="true" />
        {unreadCount > 0 && (
          <span className="message-archive-badge">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Panneau d'archive */}
      {isOpen && (
        <>
          <div className="message-archive-backdrop" onClick={togglePanel} />
          <div className="message-archive-panel">
            {/* Header */}
            <div className="message-archive-header">
              <span>Historique des messages</span>
              <div>
                {unreadCount > 0 && (
                  <button
                    className="message-archive-mark-all"
                    onClick={markAllMessagesRead}
                    title="Tout marquer comme lu"
                  >
                    <CheckCheck className="hub-icon" aria-hidden="true" />
                    <span className="sr-only">Tout marquer comme lu</span>
                  </button>
                )}
                <button className="message-archive-close" onClick={togglePanel} title="Fermer">
                  <X className="hub-icon" aria-hidden="true" />
                  <span className="sr-only">Fermer</span>
                </button>
              </div>
            </div>

            {/* Liste messages */}
            <div className="message-archive-list">
              {(!unreadMessages || unreadMessages.length === 0) ? (
                <p className="message-archive-empty">Aucun message</p>
              ) : (
                unreadMessages.map((m, idx) => (
                  <div
                    key={m.id || idx}
                    className={`${getPriorityClass(m.priority)} ${m.is_read ? 'read' : 'unread'}`}
                  >
                    <div className="message-archive-msg-header">
                      <strong>{m.title}</strong>
                      <span className="message-archive-msg-time">
                        {formatTime(m.created_at)}
                      </span>
                    </div>
                    {m.body && (
                      <div className="message-archive-msg-body">{m.body}</div>
                    )}
                    <div className="message-archive-msg-footer">
                      <span className="message-archive-msg-sender">
                        {m.sender_app_slug || m.sender_type}
                      </span>
                      <div>
                        {m.action_url && (
                          <a
                            href={m.action_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="message-archive-msg-action"
                          >
                            {m.action_label || 'Ouvrir'}
                          </a>
                        )}
                        {!m.is_read && (
                          <button
                            onClick={(e) => handleMarkRead(e, m.id)}
                            className="message-archive-msg-read"
                          >
                            <Check className="hub-icon" aria-hidden="true" /> Lu
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}
