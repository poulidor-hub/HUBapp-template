import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useConfig } from './ConfigContext'
import config from '../config'

const AuthContext = createContext(null)

// Décoder le token JWT (sans validation - la validation se fait côté serveur)
function decodeToken(token) {
  if (!token) return null
  
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    
    const payload = parts[1]
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(decoded)
  } catch (error) {
    console.error('Erreur décodage token:', error)
    return null
  }
}

export function AuthProvider({ children }) {
  const appConfig = useConfig()
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(() => 
    localStorage.getItem(config.storageKeys.accessToken)
  )

  // Décoder et vérifier le token au chargement
  useEffect(() => {
    if (token) {
      const decoded = decodeToken(token)
      if (decoded && decoded.exp) {
        const now = Math.floor(Date.now() / 1000)
        if (decoded.exp > now) {
          setUser(decoded)
        } else {
          // Token expiré
          logout()
        }
      }
    }
  }, [token])

  // Gérer le callback de connexion depuis le Hub
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const accessToken = urlParams.get('token') || urlParams.get('access_token')
    const refreshToken = urlParams.get('refresh_token')
    const error = urlParams.get('error')

    if (accessToken) {
      console.log('✅ Token reçu du Hub')
      localStorage.setItem(config.storageKeys.accessToken, accessToken)
      setToken(accessToken)
      
      if (refreshToken) {
        localStorage.setItem(config.storageKeys.refreshToken, refreshToken)
      }
      
      // Nettoyer l'URL
      window.history.replaceState({}, document.title, window.location.pathname)
    } else if (error) {
      console.error('❌ Erreur d\'authentification:', error)
      alert(`Erreur de connexion: ${error}`)
      window.history.replaceState({}, document.title, window.location.pathname)
    }
  }, [])

  const login = useCallback(() => {
    const callbackUrl = encodeURIComponent(window.location.origin + window.location.pathname)
    const hubLoginUrl = `${appConfig.hubFrontendUrl}?callback=${callbackUrl}`
    console.log('🔐 Redirection vers le Hub:', hubLoginUrl)
    window.location.href = hubLoginUrl
  }, [appConfig.hubFrontendUrl])

  const logout = useCallback(() => {
    localStorage.removeItem(config.storageKeys.accessToken)
    localStorage.removeItem(config.storageKeys.refreshToken)
    setToken(null)
    setUser(null)
    
    // Rediriger vers le Hub pour déconnexion complète
    const callbackUrl = encodeURIComponent(window.location.origin + window.location.pathname)
    const hubLogoutUrl = `${appConfig.hubFrontendUrl}?action=logout&callback=${callbackUrl}`
    console.log('🚪 Déconnexion via le Hub')
    window.location.href = hubLogoutUrl
  }, [appConfig.hubFrontendUrl])

  const refreshAccessToken = useCallback(async () => {
    const refreshToken = localStorage.getItem(config.storageKeys.refreshToken)
    if (!refreshToken) {
      console.error('Pas de refresh token disponible')
      return false
    }

    try {
      const response = await fetch(`${appConfig.hubApiUrl}/api/auth/token/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken })
      })

      if (response.ok) {
        const data = await response.json()
        localStorage.setItem(config.storageKeys.accessToken, data.access_token)
        setToken(data.access_token)
        
        if (data.refresh_token) {
          localStorage.setItem(config.storageKeys.refreshToken, data.refresh_token)
        }
        
        console.log('✅ Token rafraîchi')
        return true
      } else {
        console.error('❌ Échec rafraîchissement token')
        logout()
        return false
      }
    } catch (error) {
      console.error('❌ Erreur rafraîchissement token:', error)
      return false
    }
  }, [appConfig.hubApiUrl, logout])

  // Fetch authentifié avec gestion automatique du refresh
  const authFetch = useCallback(async (url, options = {}) => {
    const fullUrl = url.startsWith('http') ? url : `${appConfig.apiUrl}${url}`
    
    if (token) {
      options.headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
      }
    }

    let response = await fetch(fullUrl, options)

    // Si 401, tenter de rafraîchir le token
    if (response.status === 401 && token) {
      const refreshed = await refreshAccessToken()
      if (refreshed) {
        const newToken = localStorage.getItem(config.storageKeys.accessToken)
        options.headers['Authorization'] = `Bearer ${newToken}`
        response = await fetch(fullUrl, options)
      }
    }

    return response
  }, [appConfig.apiUrl, token, refreshAccessToken])

  // Récupérer le rôle de l'utilisateur pour l'app courante
  const getAppRole = useCallback(() => {
    if (!user || !user.apps) return null
    return user.apps[appConfig.appSlug] || null
  }, [user, appConfig.appSlug])

  // Vérifier si l'utilisateur a au moins le rôle spécifié
  const hasMinRole = useCallback((minRole) => {
    const roleHierarchy = { viewer: 1, user: 2, manager: 3, admin: 4 }
    const userRole = getAppRole()
    
    if (!userRole) return false
    if (user?.roles?.includes('admin')) return true // Admin global
    
    return (roleHierarchy[userRole] || 0) >= (roleHierarchy[minRole] || 0)
  }, [user, getAppRole])

  const value = {
    user,
    token,
    isAuthenticated: !!user,
    login,
    logout,
    authFetch,
    getAppRole,
    hasMinRole
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
