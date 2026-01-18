import React, { createContext, useContext, useState, useEffect } from 'react'
import config from '../config'

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

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
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
      
      // IMPORTANT: En HTTPS, utiliser le proxy /hub/ pour éviter Mixed Content
      // Le proxy nginx redirige /hub/* vers le Hub HTTP interne
      const isHttps = window.location.protocol === 'https:'
      const hubApiUrl = isHttps 
        ? `${window.location.origin}/hub`  // Proxy nginx
        : (data.hub_api_url || config.hubApiUrl)
      const hubFrontendUrl = data.hub_frontend_url || config.hubFrontendUrl
      
      setAppConfig({
        appSlug: data.app_slug || config.appSlug,
        apiUrl: config.apiUrl,  // L'API locale utilise l'hostname du navigateur
        hubApiUrl,              // URL du Hub fournie par le backend (via HUB_HOST)
        hubFrontendUrl,         // URL frontend Hub fournie par le backend
        loaded: true,
        error: null
      })
      
      console.log('✅ Configuration chargée:', data)
      console.log('📌 URLs utilisées:', {
        apiUrl: config.apiUrl,
        hubApiUrl,
        hubFrontendUrl
      })
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
  }

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
