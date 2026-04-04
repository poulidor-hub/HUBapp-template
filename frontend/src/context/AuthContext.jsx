import React, { createContext, useContext, useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useConfig } from './ConfigContext'
import config from '../config'

const AuthContext = createContext(null)

// Helper: En HTTPS, utiliser le proxy /hub/ pour éviter Mixed Content
function getHubApiUrl(configHubApiUrl) {
  if (window.location.protocol === 'https:') {
    return `${window.location.origin}/hub`
  }
  return configHubApiUrl
}

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
  const [unreadMessages, setUnreadMessages] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [activeMessages, setActiveMessages] = useState([])

  // URL du Hub avec support du proxy HTTPS
  const hubApiUrl = useMemo(() => 
    getHubApiUrl(appConfig.hubApiUrl), 
    [appConfig.hubApiUrl]
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

  // Référence pour éviter le rafraîchissement en double
  const refreshingRef = useRef(false)

  const refreshAccessToken = useCallback(async () => {
    // Éviter les rafraîchissements concurrents
    if (refreshingRef.current) {
      console.log('⏳ Rafraîchissement déjà en cours...')
      return false
    }
    
    const refreshToken = localStorage.getItem(config.storageKeys.refreshToken)
    if (!refreshToken) {
      console.error('Pas de refresh token disponible')
      return false
    }

    refreshingRef.current = true
    try {
      const response = await fetch(`${hubApiUrl}/api/auth/token/refresh`, {
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
    } finally {
      refreshingRef.current = false
    }
  }, [hubApiUrl, logout])

  // Écouter les événements SSE du Hub pour les changements de permissions
  useEffect(() => {
    if (!user || !hubApiUrl) return
    
    let eventSource = null
    let reconnectTimeout = null
    
    const connectSSE = () => {
      try {
        const sseUrl = `${hubApiUrl}/api/events/stream`
        console.log('🔌 Connexion SSE au Hub:', sseUrl)
        eventSource = new EventSource(sseUrl)
        
        eventSource.onopen = () => {
          console.log('✅ SSE connecté - écoute des changements de permissions')
        }
        
        eventSource.onmessage = async (event) => {
          try {
            const data = JSON.parse(event.data)
            
            // Ignorer les ping keep-alive
            if (data.type === 'ping' || data.type === 'connected') return
            
            console.log('📡 SSE event:', data.type, data.data)
            
            // Changement de permissions de l'utilisateur courant
            if (data.type === 'user_permissions_changed') {
              if (data.data?.username === user.sub) {
                console.log('🔄 Vos permissions ont changé, rafraîchissement du token...')
                const refreshed = await refreshAccessToken()
                if (refreshed) {
                  console.log('✅ Permissions mises à jour')
                }
              }
            }
            
            // Déconnexion forcée par l'admin
            if (data.type === 'force_logout') {
              if (data.data?.username === user.sub) {
                console.log('🚪 Déconnexion forcée par l\'administrateur')
                alert('Votre session a été révoquée par un administrateur.')
                logout()
              }
            }
            
            // Nouvelle application ajoutée/approuvée - rafraîchir pour obtenir les nouveaux accès
            if (data.type === 'apps_updated') {
              if (data.data?.action === 'approved' || data.data?.action === 'created') {
                console.log('🔄 Nouvelle application disponible, rafraîchissement du token...')
                await refreshAccessToken()
              }
            }

            // Message utilisateur reçu via SSE
            if (data.type === 'user_message') {
              console.log('📩 Nouveau message:', data.data?.title)
              setUnreadMessages(prev => [data.data, ...prev])
              setUnreadCount(prev => prev + 1)
              setActiveMessages(prev => [data.data, ...prev])
            }
            
          } catch (e) {
            console.warn('SSE: erreur parsing message', e)
          }
        }
        
        eventSource.onerror = () => {
          console.warn('⚠️ SSE déconnecté, reconnexion dans 10s...')
          eventSource?.close()
          reconnectTimeout = setTimeout(connectSSE, 10000)
        }
        
      } catch (e) {
        console.warn('SSE: impossible de créer la connexion', e)
      }
    }
    
    connectSSE()
    
    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (eventSource) {
        eventSource.close()
        console.log('🔌 SSE déconnecté')
      }
    }
  }, [user, hubApiUrl, refreshAccessToken, logout])

  // Charger les messages non-lus depuis le Hub au login
  useEffect(() => {
    if (!user || !hubApiUrl || !token) return

    const loadMessages = async () => {
      try {
        // Charger le compteur non-lus
        const countRes = await fetch(`${hubApiUrl}/api/messages/me/unread-count`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (countRes.ok) {
          const countData = await countRes.json()
          setUnreadCount(countData.count || 0)
        }

        // Charger les messages
        const msgRes = await fetch(`${hubApiUrl}/api/messages/me`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (msgRes.ok) {
          const msgData = await msgRes.json()
          setUnreadMessages(msgData || [])
          // Peupler le bandeau avec les messages non-lus
          setActiveMessages((msgData || []).filter(m => !m.is_read))
        }
      } catch (e) {
        console.warn('Messages: impossible de charger les messages', e)
      }
    }

    loadMessages()
  }, [user, hubApiUrl, token])

  // Marquer un message comme lu
  const markMessageRead = useCallback(async (messageId) => {
    try {
      const res = await fetch(`${hubApiUrl}/api/messages/${messageId}/read`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        setUnreadMessages(prev => prev.map(m =>
          m.id === messageId ? { ...m, is_read: true } : m
        ))
        setUnreadCount(prev => Math.max(0, prev - 1))
      }
    } catch (e) {
      console.warn('Messages: erreur marquage lu', e)
    }
  }, [hubApiUrl, token])

  // Marquer tous les messages comme lus
  const markAllMessagesRead = useCallback(async () => {
    try {
      const res = await fetch(`${hubApiUrl}/api/messages/read-all`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        setUnreadMessages(prev => prev.map(m => ({ ...m, is_read: true })))
        setUnreadCount(0)
      }
    } catch (e) {
      console.warn('Messages: erreur marquage tous lus', e)
    }
  }, [hubApiUrl, token])

  // Fermer un message du bandeau (le retire du bandeau + marque lu)
  const dismissMessage = useCallback(async (messageId) => {
    setActiveMessages(prev => prev.filter(m => m.id !== messageId))
    await markMessageRead(messageId)
  }, [markMessageRead])

  // Fermer tous les messages du bandeau
  const dismissAllMessages = useCallback(async () => {
    setActiveMessages([])
    await markAllMessagesRead()
  }, [markAllMessagesRead])

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
    
    return (roleHierarchy[userRole] || 0) >= (roleHierarchy[minRole] || 0)
  }, [user, getAppRole])

  // Force le rafraîchissement du token (utile après modification des droits)
  const forceRefreshToken = useCallback(async () => {
    console.log('🔄 Rafraîchissement forcé du token...')
    return await refreshAccessToken()
  }, [refreshAccessToken])

  const value = {
    user,
    token,
    isAuthenticated: !!user,
    login,
    logout,
    authFetch,
    getAppRole,
    hasMinRole,
    refreshAccessToken: forceRefreshToken,
    // Messages
    unreadMessages,
    unreadCount,
    markMessageRead,
    markAllMessagesRead,
    // Bandeau messages actifs
    activeMessages,
    dismissMessage,
    dismissAllMessages,
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
