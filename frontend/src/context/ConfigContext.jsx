import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import config, { APP_VERSION } from '../config'

const ConfigContext = createContext(null)

export function ConfigProvider({ children }) {
  const [appConfig, setAppConfig] = useState({
    appSlug: config.appSlug,
    apiUrl: config.apiUrl,
    hubApiUrl: config.hubApiUrl,
    hubFrontendUrl: config.hubFrontendUrl,
    loaded: false,
    error: null
  })

  const checkVersion = useCallback(async () => {
    // Ne pas vérifier en mode dev (pas de version embarquée)
    if (APP_VERSION === 'dev') return
    // Guard anti-boucle : un seul reload par session
    if (sessionStorage.getItem('version_reload_attempted') === APP_VERSION) return

    try {
      const res = await fetch(`${config.apiUrl}/api/version`, {
        method: 'GET',
        signal: AbortSignal.timeout(3000)
      })
      if (!res.ok) return
      const { version } = await res.json()

      if (version && version !== APP_VERSION) {
        console.warn(`⚠️ Version mismatch : frontend=${APP_VERSION}, serveur=${version} → reload`)
        sessionStorage.setItem('version_reload_attempted', APP_VERSION)
        window.location.reload()
      }
    } catch {
      // Silencieux : pas critique si la vérification échoue
    }
  }, [])

  const loadConfig = useCallback(async () => {
    try {
      console.log(`🔄 Chargement config depuis ${config.apiUrl}/api/config...`)
      
      const response = await fetch(`${config.apiUrl}/api/config`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000)
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()
      
      const isViteDevServer = window.location.port === '3000'
      const hubApiUrl = isViteDevServer
        ? (data.hub_api_url || config.hubApiUrl)
        : `${window.location.origin}/hub`
      const hubFrontendUrl = data.hub_frontend_url || config.hubFrontendUrl
      
      setAppConfig({
        appSlug: data.app_slug || config.appSlug,
        apiUrl: config.apiUrl,
        hubApiUrl,
        hubFrontendUrl,
        loaded: true,
        error: null
      })
      
      console.log('✅ Configuration chargée:', data)
      console.log('📌 URLs utilisées:', {
        apiUrl: config.apiUrl,
        hubApiUrl,
        hubFrontendUrl
      })

      // Vérification de version : comparer la version embarquée avec celle du serveur
      checkVersion()
    } catch (error) {
      console.error('❌ Erreur chargement config:', error)
      
      // Utiliser les valeurs par défaut de config.js
      setAppConfig(prev => ({
        ...prev,
        loaded: true,
        error: error.message
      }))
      
      console.warn('⚠️ Utilisation des valeurs par défaut')
    }
  }, [checkVersion])

  useEffect(() => {
    loadConfig()
  }, [loadConfig])

  return (
    <ConfigContext.Provider value={appConfig}>
      {children}
    </ConfigContext.Provider>
  )
}

export function useConfig() {
  const context = useContext(ConfigContext)
  if (!context) {
    throw new Error('useConfig must be used within a ConfigProvider')
  }
  return context
}
