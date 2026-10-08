import React from 'react'
import { ShieldAlert } from 'lucide-react'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h2><ShieldAlert className="hub-icon" aria-hidden="true" /> Une erreur inattendue est survenue</h2>
          <p>
            {this.state.error?.message || 'Erreur inconnue'}
          </p>
          <button
            className="hub-button hub-button-secondary"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Réessayer
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export default ErrorBoundary
