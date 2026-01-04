/**
 * Configuration du frontend.
 * Les variables d'environnement sont injectées par Vite au build time.
 * En production, elles viennent du .env via Docker.
 */

// Variables d'environnement Vite (préfixées par VITE_)
const env = {
  API_PORT: import.meta.env.VITE_API_PORT || '9045',
  HUB_API_PORT: import.meta.env.VITE_HUB_API_PORT || '8000',
  HUB_FRONTEND_PORT: import.meta.env.VITE_HUB_FRONTEND_PORT || '80',
  APP_SLUG: import.meta.env.VITE_APP_SLUG || 'mon-app',
}

// Construire les URLs dynamiquement basées sur l'hostname du navigateur
const getHost = () => {
  if (typeof window !== 'undefined') {
    return window.location.hostname
  }
  return 'localhost'
}

const config = {
  // Slug de l'application
  appSlug: env.APP_SLUG,
  
  // URLs construites dynamiquement
  get apiUrl() {
    return `http://${getHost()}:${env.API_PORT}`
  },
  
  get hubApiUrl() {
    return `http://${getHost()}:${env.HUB_API_PORT}`
  },
  
  get hubFrontendUrl() {
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
