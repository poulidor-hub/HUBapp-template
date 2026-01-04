/**
 * Configuration du frontend.
 * Les valeurs sont chargées depuis l'API backend /api/config.
 * Les ports sont injectés via les variables d'environnement Docker.
 */

const config = {
    // Slug de l'application (doit correspondre au backend)
    appSlug: 'mon-app',
    
    // URLs - Seront chargées depuis /api/config
    apiUrl: '',
    hubApiUrl: '',
    hubFrontendUrl: '',
    
    // Ports injectés par Docker (voir Dockerfile.frontend)
    // Ces valeurs sont remplacées au démarrage du container par envsubst
    injectedApiPort: '${API_PORT}',
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
 * Utilise uniquement le port API configuré dans le .env (API_PORT).
 */
async function loadConfig() {
    try {
        // Utiliser l'hostname du navigateur et le port API injecté par Docker
        const host = window.location.hostname;
        // Le port est injecté par le script de démarrage Docker (envsubst)
        const apiPort = config.injectedApiPort !== '__API_PORT__' 
            ? config.injectedApiPort 
            : window.location.port || '80';  // Fallback: même port que le frontend
        const apiUrl = `http://${host}:${apiPort}`;
        
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
        config.apiUrl = data.api_url || apiUrl;
        config.hubApiUrl = data.hub_api_url;
        config.hubFrontendUrl = data.hub_frontend_url;
        
        console.log('✅ Configuration chargée:', config);
    } catch (error) {
        console.error('❌ Erreur chargement config:', error);
        
        // Valeurs par défaut en cas d'erreur - utiliser les ports injectés
        const host = window.location.hostname;
        const apiPort = config.injectedApiPort !== '__API_PORT__' ? config.injectedApiPort : window.location.port;
        const hubApiPort = config.injectedHubApiPort !== '__HUB_API_PORT__' ? config.injectedHubApiPort : '8000';
        const hubFrontendPort = config.injectedHubFrontendPort !== '__HUB_FRONTEND_PORT__' ? config.injectedHubFrontendPort : '80';
        
        config.apiUrl = `http://${host}:${apiPort}`;
        config.hubApiUrl = `http://${host}:${hubApiPort}`;
        config.hubFrontendUrl = `http://${host}:${hubFrontendPort}`;
        
        console.warn('⚠️ Utilisation des valeurs par défaut:', config);
    }
}
