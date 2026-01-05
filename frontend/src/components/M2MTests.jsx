import React, { useState, useEffect } from 'react'
import { useConfig } from '../context/ConfigContext'
import { useAuth } from '../context/AuthContext'

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

  // Vérifier si l'utilisateur est admin
  const isAdmin = user?.roles?.includes('admin') || 
                  user?.apps?.[config.appSlug] === 'admin'

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
      const response = await fetch(`${config.apiUrl}/api/m2m/status`)
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
      // Construire l'URL de test (health check du service)
      const testUrl = `${service.api_url}/api/health`
      
      const response = await fetch(`${config.apiUrl}/api/m2m/test-call?target_url=${encodeURIComponent(testUrl)}`, {
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
      
      setTestResults(prev => ({
        ...prev,
        [serviceKey]: {
          success: data.success,
          status: data.status_code,
          response: data.response,
          error: data.error,
          timestamp: new Date().toLocaleTimeString()
        }
      }))
    } catch (err) {
      setTestResults(prev => ({
        ...prev,
        [serviceKey]: {
          success: false,
          error: err.message,
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
      <h2>🔗 Tests M2M (Machine-to-Machine)</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '15px' }}>
        Section réservée aux administrateurs - Test de la communication inter-services via le Hub.
      </p>

      {/* Erreur globale */}
      {error && (
        <div className="test-result error" style={{ marginBottom: '15px' }}>
          ⚠️ {error}
        </div>
      )}

      {/* Statut M2M de l'application */}
      <div className="m2m-section">
        <h3>📊 Statut M2M de l'application</h3>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
          <button 
            className="btn btn-small btn-secondary" 
            onClick={fetchM2MStatus}
            disabled={loading.status}
          >
            {loading.status ? '...' : '🔄 Actualiser'}
          </button>
        </div>
        
        {m2mStatus && (
          <div className="m2m-status-card">
            <div className={`status-badge ${m2mStatus.registered ? 'success' : 'error'}`}>
              {m2mStatus.registered ? '✅ Enregistré' : '❌ Non enregistré'}
            </div>
            {m2mStatus.client_id && (
              <div className="status-detail">
                <strong>Client ID:</strong> <code>{m2mStatus.client_id}</code>
              </div>
            )}
            <div className="status-detail">
              <strong>Token M2M:</strong> 
              {m2mStatus.can_get_token ? (
                <span className="text-success"> ✅ Disponible</span>
              ) : (
                <span className="text-error"> ❌ Indisponible</span>
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
      <div className="m2m-section" style={{ marginTop: '20px' }}>
        <h3>🔍 Services M2M disponibles</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9em', marginBottom: '10px' }}>
          Interroge le Hub pour découvrir les APIs partagées (is_shared_service=true).
        </p>
        
        <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
          <button 
            className="btn btn-primary" 
            onClick={discoverServices}
            disabled={loading.discover || !m2mStatus?.can_get_token}
          >
            {loading.discover ? '⏳ Recherche...' : '🔍 Découvrir les services'}
          </button>
          
          {sharedServices.length > 0 && (
            <button 
              className="btn btn-secondary" 
              onClick={testAllServices}
              disabled={Object.values(loading.test).some(v => v)}
            >
              🧪 Tester tous
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
                  <button 
                    className="btn btn-small btn-primary"
                    onClick={() => testService(service)}
                    disabled={loading.test[service.slug]}
                  >
                    {loading.test[service.slug] ? '...' : '🧪 Tester'}
                  </button>
                </div>
                
                {service.description && (
                  <div className="service-description">{service.description}</div>
                )}
                
                <div className="service-url">
                  <code>{service.api_url}</code>
                </div>
                
                {/* Résultat du test */}
                {testResults[service.slug] && (
                  <div className={`test-result ${testResults[service.slug].success ? 'success' : 'error'}`}>
                    {testResults[service.slug].success ? (
                      <>
                        ✅ <strong>{testResults[service.slug].status}</strong> OK
                        <span className="test-time">({testResults[service.slug].timestamp})</span>
                        {testResults[service.slug].response && (
                          <pre className="test-response">
                            {typeof testResults[service.slug].response === 'string' 
                              ? testResults[service.slug].response.substring(0, 200)
                              : JSON.stringify(testResults[service.slug].response, null, 2).substring(0, 200)}
                          </pre>
                        )}
                      </>
                    ) : (
                      <>
                        ❌ <strong>{testResults[service.slug].status || 'Erreur'}</strong>
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
              <p>⏳ Recherche des services en cours...</p>
            ) : (
              <p>Cliquez sur "Découvrir les services" pour interroger le Hub.</p>
            )}
          </div>
        )}
      </div>

      {/* Info sur le fonctionnement */}
      <div className="m2m-info" style={{ marginTop: '20px', padding: '15px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
        <h4 style={{ margin: '0 0 10px 0' }}>ℹ️ Comment ça fonctionne</h4>
        <ul style={{ margin: 0, paddingLeft: '20px', color: 'var(--text-secondary)' }}>
          <li><strong>Découverte</strong>: Appelle <code>GET /api/apps/discover</code> sur le Hub avec un token M2M</li>
          <li><strong>Test</strong>: Effectue un appel M2M vers le <code>/api/health</code> du service cible</li>
          <li><strong>Authentification</strong>: Utilise le Service Account de cette application</li>
        </ul>
      </div>
    </div>
  )
}

export default M2MTests
