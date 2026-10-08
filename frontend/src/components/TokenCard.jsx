import { useState } from 'react'
import { Check, Copy, KeyRound } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

function TokenCard() {
  const { user, token } = useAuth()
  const [copied, setCopied] = useState(false)

  if (!user) return null

  const copyToken = () => {
    if (!token) return
    navigator.clipboard.writeText(token).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="hub-panel hub-panel--padded">
      <div className="token-header">
        <h2><KeyRound className="hub-icon" aria-hidden="true" /> Token JWT</h2>
        <button
          className="hub-button hub-button-secondary hub-button--sm"
          onClick={copyToken}
          disabled={!token}
        >
          {copied ? (
            <><Check className="hub-icon" aria-hidden="true" /> Copié</>
          ) : (
            <><Copy className="hub-icon" aria-hidden="true" /> Copier</>
          )}
        </button>
      </div>
      <div className="token-display">
        {JSON.stringify(user, null, 2)}
      </div>
    </div>
  )
}

export default TokenCard
