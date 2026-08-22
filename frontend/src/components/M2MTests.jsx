import React, { useState, useEffect } from 'react'
import {
  Activity, AlertTriangle, Check, FlaskConical, Info, Lightbulb, Link2,
  List, Loader2, RefreshCw, Search, Target, XCircle,
} from 'lucide-react'
import { useConfig } from '../context/ConfigContext'
import { useAuth } from '../context/AuthContext'

// Liste des endpoints disponibles basée sur le template HUBapp
const AVAILABLE_ENDPOINTS = [
  // Endpoints publics (sans authentification)
  { 
    value: '/api/health', 
    label: 'Health Check', 
    category: 'Public',
    method: 'GET',
    description: 'Vérifie que l\'API est opérationnelle'
  },
  { 
    value: '/api/health/detailed', 
    label: 'Health Détaillé', 
    category: 'Public',
    method: 'GET',
    description: 'Health check avec infos sur les dépendances'
  },
  { 
    value: '/api/version', 
    label: 'Version', 
    category: 'Public',
    method: 'GET',
    description: 'Retourne la version de l\'application'
  },
  { 
    value: '/api/config', 
    label: 'Configuration', 
    category: 'Public',
    method: 'GET',
    description: 'Configuration publique pour le frontend'
  },
  { 
    value: '/api/public', 
    label: 'Public Endpoint', 
    category: 'Public',
    method: 'GET',
    description: 'Endpoint accessible sans authentification'
  },
  // Endpoints protégés (authentification requise)
  { 
    value: '/api/protected', 
    label: 'Protected', 
    category: 'Protégé',
    method: 'GET',
    description: 'Requiert un token valide'
  },
  { 
    value: '/api/me', 
    label: 'User Info', 
    category: 'Protégé',
    method: 'GET',
    description: 'Informations de l\'utilisateur/service connecté'
  },
  // Endpoints par rôle
  { 
    value: '/api/viewer-only', 
    label: 'Viewer+', 
    category: 'Rôles',
    method: 'GET',
    description: 'Accessible aux rôles viewer, user, manager, admin'
  },
  { 
    value: '/api/user-only', 
    label: 'User+', 
    category: 'Rôles',
    method: 'GET',
    description: 'Accessible aux rôles user, manager, admin'
  },
  { 
    value: '/api/manager-only', 
    label: 'Manager+', 
    category: 'Rôles',
    method: 'GET',
    description: 'Accessible aux rôles manager et admin'
  },
  { 
    value: '/api/admin-only', 
    label: 'Admin', 
    category: 'Rôles',
    method: 'GET',
    description: 'Accessible uniquement aux admins'
  },
  { 
    value: '/api/service-only', 
    label: 'Service Account', 
    category: 'M2M',
    method: 'GET',
    description: 'Réservé aux service accounts (M2M)'
  },
  // Endpoints données
  { 
    value: '/api/items', 
    label: 'Liste Items', 
    category: 'Données',
    method: 'GET',
    description: 'Liste les items (paginé)'
  },
]

// Grouper les endpoints par catégorie
const ENDPOINT_CATEGORIES = [...new Set(AVAILABLE_ENDPOINTS.map(e => e.category))]

function M2MTests() {
  const config = useConfig()
  const { token, user } = useAuth()
  
  // États
  const [m2mStatus, setM2mStatus] = useState(null)
  const [sharedServices, setSharedServices] = useState([])
  const [loading, setLoading] = useState({
    status: false,
    discover: false,
    test: {}
  })
  const [testResults, setTestResults] = useState({})
  const [error, setError] = useState(null)
  // État pour l'endpoint sélectionné par service
  const [selectedEndpoints, setSelectedEndpoints] = useState({})

  // Vérifier si l'utilisateur est admin
  const isAdmin = user?.apps?.[config.appSlug] === 'admin'

  // Charger le statut M2M au montage
  useEffect(() => {
    if (isAdmin) {
      fetchM2MStatus()
    }
  }, [isAdmin])

  /**
   * Récupère le statut M2M de l'application
   */
  const fetchM2MStatus = async () => {
    setLoading(prev => ({ ...prev, status: true }))
    setError(null)
    
    try {
      const response = await fetch(`${config.apiUrl}/api/m2m/status`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      const contentType = response.headers.get('content-type')
      
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text()
        throw new Error(`Réponse non-JSON: ${text.substring(0, 100)}`)
      }
      
      const data = await response.json()
      setM2mStatus(data)
    } catch (err) {
      setError(`Erreur statut M2M: ${err.message}`)
      setM2mStatus(null)
    } finally {
      setLoading(prev => ({ ...prev, status: false }))
    }
  }

  /**
   * Découvre les services M2M disponibles via le Hub
   */
  const discoverServices = async () => {
    setLoading(prev => ({ ...prev, discover: true }))
    setError(null)
    
    try {
      const response = await fetch(`${config.apiUrl}/api/m2m/discover`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      
      const contentType = response.headers.get('content-type')
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text()
        throw new Error(`Réponse non-JSON: ${text.substring(0, 100)}`)
      }
      
      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.detail || `Erreur ${response.status}`)
      }
      
      // Le backend retourne "services" (pas "shared_services")
      setSharedServices(data.services || data.shared_services || [])
    } catch (err) {
      setError(`Erreur découverte: ${err.message}`)
      setSharedServices([])
    } finally {
      setLoading(prev => ({ ...prev, discover: false }))
    }
  }

  /**
   * Teste la connectivité M2M vers un service
   */
  const testService = async (service) => {
    const serviceKey = service.slug
    setLoading(prev => ({ 
      ...prev, 
      test: { ...prev.test, [serviceKey]: true } 
    }))
    
    try {
      // Récupérer l'endpoint sélectionné pour ce service (par défaut /api/health)
      const selectedEndpoint = selectedEndpoints[serviceKey] || '/api/health'
      const endpointInfo = AVAILABLE_ENDPOINTS.find(e => e.value === selectedEndpoint)
      
      // Utiliser l'endpoint sécurisé /api/m2m/call/{slug} avec le slug du service
      const params = new URLSearchParams({
        endpoint: selectedEndpoint,
        method: endpointInfo?.method || 'GET'
      })
      
      const response = await fetch(`${config.apiUrl}/api/m2m/call/${encodeURIComponent(service.slug)}?${params}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      
      const contentType = response.headers.get('content-type')
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text()
        throw new Error(`Réponse non-JSON: ${text.substring(0, 100)}`)
      }
      
      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.detail || `Erreur ${response.status}`)
      }
      
      setTestResults(prev => ({
        ...prev,
        [serviceKey]: {
          success: data.success !== false,
          status: response.status,
          response: data.response,
          error: data.error || data.detail,
          endpoint: selectedEndpoint,
          endpointLabel: endpointInfo?.label || selectedEndpoint,
          timestamp: new Date().toLocaleTimeString()
        }
      }))
    } catch (err) {
      const selectedEndpoint = selectedEndpoints[serviceKey] || '/api/health'
      const endpointInfo = AVAILABLE_ENDPOINTS.find(e => e.value === selectedEndpoint)
      setTestResults(prev => ({
        ...prev,
        [serviceKey]: {
          success: false,
          error: err.message,
          endpoint: selectedEndpoint,
          endpointLabel: endpointInfo?.label || selectedEndpoint,
          timestamp: new Date().toLocaleTimeString()
        }
      }))
    } finally {
      setLoading(prev => ({ 
        ...prev, 
        test: { ...prev.test, [serviceKey]: false } 
      }))
    }
  }

  /**
   * Teste tous les services découverts
   */
  const testAllServices = async () => {
    for (const service of sharedServices) {
      await testService(service)
      // Petit délai entre chaque test
      await new Promise(r => setTimeout(r, 300))
    }
  }

  // Ne rien afficher si pas admin
  if (!isAdmin) {
    return null
  }

  return (
    <div className="card m2m-tests">
      <h2><Link2 className="hub-icon" aria-hidden="true" /> Tests M2M (Machine-to-Machine)</h2>
      <p className="card-intro">
        Section réservée aux administrateurs - Test de la communication inter-services via le Hub.
      </p>

      {/* Erreur globale */}
      {error && (
        <div className="test-result error">
          <AlertTriangle className="hub-icon" aria-hidden="true" /> {error}
        </div>
      )}

      {/* Statut M2M de l'application */}
      <div className="m2m-section">
        <h3><Activity className="hub-icon" aria-hidden="true" /> Statut M2M de l'application</h3>
        <div className="m2m-toolbar">
          <button
            className="btn btn-small btn-secondary"
            onClick={fetchM2MStatus}
            disabled={loading.status}
          >
            {loading.status
              ? <Loader2 className="hub-icon" aria-hidden="true" />
              : <RefreshCw className="hub-icon" aria-hidden="true" />}
            {' '}{loading.status ? 'Chargement...' : 'Actualiser'}
          </button>
        </div>

        {m2mStatus && (
          <div className="m2m-status-card">
            <div className={`status-badge ${m2mStatus.registered ? 'success' : 'error'}`}>
              {m2mStatus.registered
                ? <><Check className="hub-icon" aria-hidden="true" /> Enregistré</>
                : <><XCircle className="hub-icon" aria-hidden="true" /> Non enregistré</>}
            </div>
            {m2mStatus.client_id && (
              <div className="status-detail">
                <strong>Client ID:</strong> <code>{m2mStatus.client_id}</code>
              </div>
            )}
            <div className="status-detail">
              <strong>Token M2M:</strong>
              {m2mStatus.can_get_token ? (
                <span className="text-success"><Check className="hub-icon" aria-hidden="true" /> Disponible</span>
              ) : (
                <span className="text-error"><XCircle className="hub-icon" aria-hidden="true" /> Indisponible</span>
              )}
            </div>
            {m2mStatus.token_preview && (
              <div className="status-detail">
                <strong>Aperçu:</strong> <code>{m2mStatus.token_preview}</code>
              </div>
            )}
            {m2mStatus.error && (
              <div className="status-detail text-error">
                <strong>Erreur:</strong> {m2mStatus.error}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Découverte des services */}
      <div className="m2m-section m2m-section-spaced">
        <h3><Search className="hub-icon" aria-hidden="true" /> Services M2M disponibles</h3>
        <p className="card-intro">
          Interroge le Hub pour découvrir les APIs partagées (is_shared_service=true).
        </p>

        <div className="m2m-actions">
          <button
            className="btn btn-primary"
            onClick={discoverServices}
            disabled={loading.discover || !m2mStatus?.can_get_token}
          >
            {loading.discover
              ? <Loader2 className="hub-icon" aria-hidden="true" />
              : <Search className="hub-icon" aria-hidden="true" />}
            {' '}{loading.discover ? 'Recherche...' : 'Découvrir les services'}
          </button>

          {sharedServices.length > 0 && (
            <button
              className="btn btn-secondary"
              onClick={testAllServices}
              disabled={Object.values(loading.test).some(v => v)}
            >
              <FlaskConical className="hub-icon" aria-hidden="true" /> Tester tous
            </button>
          )}
        </div>

        {/* Liste des services découverts */}
        {sharedServices.length > 0 ? (
          <div className="services-list">
            {sharedServices.map(service => (
              <div key={service.slug} className="service-card">
                <div className="service-header">
                  <div className="service-info">
                    <strong>{service.name || service.slug}</strong>
                    <span className="service-slug">({service.slug})</span>
                  </div>
                  <div className="service-actions">
                    {/* Dropdown de sélection d'endpoint */}
                    <select
                      className="endpoint-select"
                      value={selectedEndpoints[service.slug] || '/api/health'}
                      onChange={(e) => setSelectedEndpoints(prev => ({
                        ...prev,
                        [service.slug]: e.target.value
                      }))}
                    >
                      {ENDPOINT_CATEGORIES.map(category => (
                        <optgroup key={category} label={`── ${category} ──`}>
                          {AVAILABLE_ENDPOINTS
                            .filter(ep => ep.category === category)
                            .map(endpoint => (
                              <option key={endpoint.value} value={endpoint.value}>
                                {endpoint.label} ({endpoint.method})
                              </option>
                            ))
                          }
                        </optgroup>
                      ))}
                    </select>
                    <button
                      className="btn btn-small btn-primary"
                      onClick={() => testService(service)}
                      disabled={loading.test[service.slug]}
                    >
                      {loading.test[service.slug]
                        ? <Loader2 className="hub-icon" aria-hidden="true" />
                        : <FlaskConical className="hub-icon" aria-hidden="true" />}
                      {' '}{loading.test[service.slug] ? 'Test...' : 'Tester'}
                    </button>
                  </div>
                </div>

                {/* Description de l'endpoint sélectionné */}
                {(() => {
                  const ep = AVAILABLE_ENDPOINTS.find(e => e.value === (selectedEndpoints[service.slug] || '/api/health'))
                  return ep?.description ? (
                    <div className="endpoint-hint">
                      <Lightbulb className="hub-icon" aria-hidden="true" /> {ep.description}
                    </div>
                  ) : null
                })()}
                
                {service.description && (
                  <div className="service-description">{service.description}</div>
                )}
                
                <div className="service-url">
                  <code>{service.api_url}</code>
                </div>
                
                {/* Résultat du test */}
                {testResults[service.slug] && (
                  <div className={`test-result ${testResults[service.slug].success ? 'success' : 'error'}`}>
                    <div className="test-endpoint-label">
                      <Target className="hub-icon" aria-hidden="true" />
                      Endpoint testé: <code>{testResults[service.slug].endpoint || '/api/health'}</code>
                    </div>
                    {testResults[service.slug].success ? (
                      <>
                        <Check className="hub-icon" aria-hidden="true" /> <strong>{testResults[service.slug].status}</strong> OK
                        <span className="test-time">({testResults[service.slug].timestamp})</span>
                        {testResults[service.slug].response && (
                          <pre className="test-response">
                            {typeof testResults[service.slug].response === 'string'
                              ? testResults[service.slug].response.substring(0, 300)
                              : JSON.stringify(testResults[service.slug].response, null, 2).substring(0, 300)}
                          </pre>
                        )}
                      </>
                    ) : (
                      <>
                        <XCircle className="hub-icon" aria-hidden="true" /> <strong>{testResults[service.slug].status || 'Erreur'}</strong>
                        <span className="test-time">({testResults[service.slug].timestamp})</span>
                        {testResults[service.slug].response && (
                          <div className="test-error">
                            {typeof testResults[service.slug].response === 'string'
                              ? testResults[service.slug].response
                              : JSON.stringify(testResults[service.slug].response)}
                          </div>
                        )}
                        {testResults[service.slug].error && (
                          <div className="test-error">{testResults[service.slug].error}</div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            {loading.discover ? (
              <p><Loader2 className="hub-icon" aria-hidden="true" /> Recherche des services en cours...</p>
            ) : (
              <p>Cliquez sur "Découvrir les services" pour interroger le Hub.</p>
            )}
          </div>
        )}
      </div>

      {/* Info sur le fonctionnement */}
      <div className="m2m-info">
        <h4><Info className="hub-icon" aria-hidden="true" /> Comment ça fonctionne</h4>
        <ul>
          <li><strong>Découverte</strong>: Appelle <code>GET /api/apps/discover</code> sur le Hub avec un token M2M</li>
          <li><strong>Endpoints</strong>: Sélectionnez l'endpoint à tester via le dropdown (basé sur le template HUBapp)</li>
          <li><strong>Test</strong>: Effectue un appel M2M vers l'endpoint sélectionné du service cible</li>
          <li><strong>Authentification</strong>: Utilise le Service Account de cette application</li>
        </ul>

        <details className="endpoint-list-details">
          <summary>
            <List className="hub-icon" aria-hidden="true" /> Liste des endpoints disponibles ({AVAILABLE_ENDPOINTS.length})
          </summary>
          <div className="endpoint-list">
            {ENDPOINT_CATEGORIES.map(category => (
              <div key={category} className="endpoint-category">
                <strong>{category}</strong>
                <ul>
                  {AVAILABLE_ENDPOINTS
                    .filter(ep => ep.category === category)
                    .map(ep => (
                      <li key={ep.value}>
                        <code>{ep.method} {ep.value}</code> - {ep.description}
                      </li>
                    ))
                  }
                </ul>
              </div>
            ))}
          </div>
        </details>
      </div>
    </div>
  )
}

export default M2MTests
