/**
 * Configuration du frontend.
 * Les variables d'environnement sont injectées par Vite au build time.
 * En production, elles viennent du .env via Docker.
 */

// Variables d'environnement Vite (préfixées par VITE_)
const env = {
  API_PORT: import.meta.env.VITE_API_PORT || '9045',
  API_HTTPS_PORT: import.meta.env.VITE_API_HTTPS_PORT || '9046',
  HUB_API_PORT: import.meta.env.VITE_HUB_API_PORT || '8000',
  HUB_FRONTEND_PORT: import.meta.env.VITE_HUB_FRONTEND_PORT || '80',
  HUB_HTTPS_PORT: import.meta.env.VITE_HUB_HTTPS_PORT || '443',
  APP_SLUG: import.meta.env.VITE_APP_SLUG || 'mon-app',
}

// Construire les URLs dynamiquement basées sur l'hostname et le protocole du navigateur
const getHost = () => {
  if (typeof window !== 'undefined') {
    return window.location.hostname
  }
  return 'localhost'
}

// Détecte automatiquement si on est en HTTPS
const getProtocol = () => {
  if (typeof window !== 'undefined') {
    return window.location.protocol
  }
  return 'http:'
}

// Retourne true si on est en HTTPS
const isHttps = () => getProtocol() === 'https:'

const config = {
  // Slug de l'application
  appSlug: env.APP_SLUG,
  
  // URLs construites dynamiquement (adapte automatiquement HTTP/HTTPS)
  get apiUrl() {
    if (isHttps()) {
      // En HTTPS, l'API passe par le proxy nginx sur le même port que le frontend
      // Cela évite les problèmes CORS avec les certificats auto-signés
      const frontendPort = window.location.port || '443'
      return `${getProtocol()}//${getHost()}:${frontendPort}`
    }
    // En HTTP, utiliser le port API direct
    return `${getProtocol()}//${getHost()}:${env.API_PORT}`
  },
  
  get hubApiUrl() {
    // Le Hub utilise le port HTTPS si on est en HTTPS
    const port = isHttps() ? env.HUB_HTTPS_PORT : env.HUB_API_PORT
    return `${getProtocol()}//${getHost()}:${port}`
  },
  
  get hubFrontendUrl() {
    // Le Hub frontend utilise le port HTTPS si on est en HTTPS
    const port = isHttps() ? env.HUB_HTTPS_PORT : env.HUB_FRONTEND_PORT
    return `${getProtocol()}//${getHost()}:${port}`
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
