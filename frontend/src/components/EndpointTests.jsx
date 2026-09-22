import { useState } from 'react'
import {
  BookOpen, Check, ClipboardList, Crown, Eye, FlaskConical, Info,
  Lock, Package, Rocket, User, XCircle,
} from 'lucide-react'
import { useConfig } from '../context/ConfigContext'
import { useAuth } from '../context/AuthContext'

// icon: composant Lucide (affiché via className="hub-icon")
const ENDPOINTS = [
  { name: 'Public', endpoint: '/api/public', description: 'Aucune authentification requise', icon: BookOpen },
  { name: 'Protected', endpoint: '/api/protected', description: 'Token valide requis (tout rôle)', icon: Lock },
  { name: 'Viewer+', endpoint: '/api/viewer-only', description: 'Rôle minimum: viewer', role: 'viewer', icon: Eye },
  { name: 'User+', endpoint: '/api/user-only', description: 'Rôle minimum: user', role: 'user', icon: User },
  { name: 'Manager+', endpoint: '/api/manager-only', description: 'Rôle minimum: manager', role: 'manager', icon: ClipboardList },
  { name: 'Admin', endpoint: '/api/admin-only', description: 'Rôle requis: admin', role: 'admin', icon: Crown },
  { name: 'Mon profil', endpoint: '/api/me', description: 'Token valide requis', icon: Info },
  { name: 'Items', endpoint: '/api/items', description: 'Public (items publics) / Auth (+ ses items)', icon: Package },
]

function EndpointTests() {
  const config = useConfig()
  const { token } = useAuth()
  const [results, setResults] = useState({})
  const [loading, setLoading] = useState({})

  const testEndpoint = async (endpoint) => {
    setLoading(prev => ({ ...prev, [endpoint]: true }))
    
    try {
      const headers = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch(`${config.apiUrl}${endpoint}`, { headers })
      
      // Vérifier le Content-Type avant de parser le JSON
      const contentType = response.headers.get('content-type')
      let data
      
      if (contentType && contentType.includes('application/json')) {
        data = await response.json()
      } else {
        // Réponse non-JSON (erreur serveur, HTML, etc.)
        const text = await response.text()
        data = { detail: `Réponse non-JSON (${response.status}): ${text.substring(0, 100)}` }
      }

      setResults(prev => ({
        ...prev,
        [endpoint]: {
          success: response.ok,
          status: response.status,
          data: response.ok 
            ? JSON.stringify(data).substring(0, 100) + '...'
            : data.detail || `Erreur ${response.status}`
        }
      }))
    } catch (error) {
      setResults(prev => ({
        ...prev,
        [endpoint]: {
          success: false,
          status: 0,
          data: error.message
        }
      }))
    }

    setLoading(prev => ({ ...prev, [endpoint]: false }))
  }

  const runAllTests = async () => {
    for (const ep of ENDPOINTS) {
      await testEndpoint(ep.endpoint)
      await new Promise(r => setTimeout(r, 200))
    }
  }

  const clearResults = () => {
    setResults({})
  }

  return (
    <>
      <div className="card">
        <h2><FlaskConical className="hub-icon" aria-hidden="true" /> Test des endpoints par rôle</h2>
        <p className="card-intro">
          Cliquez sur "Tester" pour vérifier votre accès à chaque endpoint.
        </p>

        <div className="test-grid">
          {ENDPOINTS.map(({ name, endpoint, description, role, icon: Icon }) => (
            <div key={endpoint} className="test-item">
              <h3>
                <span className="service-info">
                  <Icon className="hub-icon" aria-hidden="true" /> {name}
                </span>
                <button
                  className="btn btn-small btn-primary"
                  onClick={() => testEndpoint(endpoint)}
                  disabled={loading[endpoint]}
                >
                  {loading[endpoint] ? '...' : 'Tester'}
                </button>
              </h3>
              <div className="endpoint">GET {endpoint}</div>
              <div className="required-role">
                {role ? (
                  <>Rôle minimum: <span className={`role-badge role-${role}`}>{role}</span></>
                ) : (
                  description
                )}
              </div>
              {results[endpoint] && (
                <div className={`test-result ${results[endpoint].success ? 'success' : 'error'}`}>
                  {results[endpoint].success ? (
                    <><Check className="hub-icon" aria-hidden="true" /> {results[endpoint].status} OK</>
                  ) : (
                    <><XCircle className="hub-icon" aria-hidden="true" /> {results[endpoint].status} {results[endpoint].data}</>
                  )}
                  {results[endpoint].success && (
                    <><br /><small>{results[endpoint].data}</small></>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h2><Rocket className="hub-icon" aria-hidden="true" /> Actions rapides</h2>
        <div className="card-actions">
          <button className="btn btn-primary" onClick={runAllTests}>
            Tester tous les endpoints
          </button>
          <button className="btn btn-secondary" onClick={clearResults}>
            Effacer les résultats
          </button>
          <a href={`${config.apiUrl}/api/docs`} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">
            <BookOpen className="hub-icon" aria-hidden="true" /> Documentation API
          </a>
        </div>
      </div>
    </>
  )
}

export default EndpointTests
