/**
 * Configuration du frontend.
 * Les valeurs sont chargées depuis l'API backend /api/config.
 * 
 * HTTPS : géré par nginx (SSL termination).
 * En HTTPS, les appels Hub passent par le proxy /hub/ pour éviter Mixed Content.
 * L'API est toujours accédée via /api/ (proxy nginx), jamais directement.
 */

const config = {
    // Slug de l'application (doit correspondre au backend)
    appSlug: 'mon-app',
    
    // URLs - Seront chargées depuis /api/config
    apiUrl: '',
    hubApiUrl: '',
    hubFrontendUrl: '',
    
    // Ports HTTP injectés par Docker (voir Dockerfile.frontend)
    injectedHubApiPort: '${HUB_API_PORT}',
    injectedHubFrontendPort: '${HUB_FRONTEND_PORT}',
    
    // Clés de stockage localStorage
    storageKeys: {
        accessToken: 'hub_token',
        refreshToken: 'hub_refresh_token',
        theme: 'theme',
        preferences: 'user_preferences'
    }
};

/**
 * Charge la configuration depuis l'API backend.
 * L'API est toujours accédée via le proxy nginx /api/.
 */
async function loadConfig() {
    try {
        // En HTTPS ou HTTP, l'API est accessible via /api/ (proxy nginx)
        const apiUrl = `${window.location.origin}`;
        
        console.log(`🔄 Chargement config depuis ${apiUrl}/api/config...`);
        
        const response = await fetch(`${apiUrl}/api/config`, { 
            method: 'GET',
            signal: AbortSignal.timeout(5000)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        config.appSlug = data.app_slug || config.appSlug;
        config.apiUrl = apiUrl;
        
        // En HTTPS, utiliser le proxy /hub/ pour éviter Mixed Content
        const isHttps = window.location.protocol === 'https:';
        if (isHttps) {
            config.hubApiUrl = `${window.location.origin}/hub`;
            config.hubFrontendUrl = data.hub_frontend_url;
        } else {
            config.hubApiUrl = data.hub_api_url;
            config.hubFrontendUrl = data.hub_frontend_url;
        }
        
        console.log('✅ Configuration chargée:', config);
    } catch (error) {
        console.error('❌ Erreur chargement config:', error);
        
        // Valeurs par défaut en cas d'erreur
        const host = window.location.hostname;
        const isHttps = window.location.protocol === 'https:';
        
        config.apiUrl = window.location.origin;
        
        if (isHttps) {
            config.hubApiUrl = `${window.location.origin}/hub`;
        } else {
            const hubApiPort = config.injectedHubApiPort !== '${HUB_API_PORT}' 
                ? config.injectedHubApiPort : '8000';
            config.hubApiUrl = `http://${host}:${hubApiPort}`;
        }
        
        const hubFrontendPort = config.injectedHubFrontendPort !== '${HUB_FRONTEND_PORT}' 
            ? config.injectedHubFrontendPort : '80';
        config.hubFrontendUrl = `http://${host}:${hubFrontendPort}`;
        
        console.warn('⚠️ Utilisation des valeurs par défaut:', config);
    }
}
