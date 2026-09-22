/**
 * Configuration du frontend.
 * Les variables d'environnement sont injectées par Vite au build time.
 * En production, elles viennent du .env via Docker.
 */

// Version de l'application (injectée au build par Vite)
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || 'dev'

// Variables d'environnement Vite (préfixées par VITE_)
const env = {
  API_PORT: import.meta.env.VITE_API_PORT || '9045',
  HUB_API_PORT: import.meta.env.VITE_HUB_API_PORT || '8000',
  HUB_FRONTEND_PORT: import.meta.env.VITE_HUB_FRONTEND_PORT || '80',
  APP_SLUG: import.meta.env.VITE_APP_SLUG || 'mon-app',
}

// Construire les URLs dynamiquement basées sur l'hostname et le protocole du navigateur
const getHost = () => {
  if (typeof window !== 'undefined') {
    return window.location.hostname
  }
  return 'localhost'
}

const isViteDevServer = () => {
  if (typeof window === 'undefined') return false
  return window.location.port === '3000'
}

const config = {
  // Slug de l'application
  appSlug: env.APP_SLUG,
  
  // URLs construites dynamiquement
  // En mode Docker/nginx : tout passe par les proxies du même origin (/api/, /hub/)
  // En mode Vite dev    : accès direct aux ports backend et Hub
  get apiUrl() {
    if (typeof window !== 'undefined' && !isViteDevServer()) {
      return window.location.origin
    }
    return `http://${getHost()}:${env.API_PORT}`
  },
  
  get hubApiUrl() {
    if (typeof window !== 'undefined' && !isViteDevServer()) {
      return `${window.location.origin}/hub`
    }
    return `http://${getHost()}:${env.HUB_API_PORT}`
  },
  
  get hubFrontendUrl() {
    // Le Hub frontend est toujours en HTTP (pas de SSL sur le Hub)
    return `http://${getHost()}:${env.HUB_FRONTEND_PORT}`
  },
  
  // Clés de stockage localStorage
  storageKeys: {
    accessToken: 'hub_token',
    refreshToken: 'hub_refresh_token',
    theme: 'theme',
    preferences: 'user_preferences'
  }
}

export default config
export { env }
