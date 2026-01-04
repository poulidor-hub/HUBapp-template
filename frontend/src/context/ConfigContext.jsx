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
      
      setAppConfig({
        appSlug: data.app_slug || config.appSlug,
        apiUrl: data.api_url || config.apiUrl,
        hubApiUrl: data.hub_api_url || config.hubApiUrl,
        hubFrontendUrl: data.hub_frontend_url || config.hubFrontendUrl,
        loaded: true,
        error: null
      })
      
      console.log('✅ Configuration chargée:', data)
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
