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
    
    // Ports HTTP injectés par Docker (voir Dockerfile.frontend)
    // Ces valeurs sont remplacées au démarrage du container par envsubst
    injectedApiPort: '${API_PORT}',
    injectedHubApiPort: '${HUB_API_PORT}',
    injectedHubFrontendPort: '${HUB_FRONTEND_PORT}',
    
    // Ports HTTPS injectés par Docker (optionnels)
    injectedApiHttpsPort: '${API_HTTPS_PORT}',
    injectedFrontendHttpsPort: '${FRONTEND_HTTPS_PORT}',
    injectedHubHttpsPort: '${HUB_HTTPS_PORT}',
    
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
 * Utilise HTTPS si le port HTTPS est configuré, sinon HTTP.
 */
async function loadConfig() {
    try {
        // Utiliser l'hostname du navigateur
        const host = window.location.hostname;
        
        // Déterminer le protocole et port de l'API
        // Priorité : HTTPS si configuré et page en HTTPS, sinon HTTP
        const isHttps = window.location.protocol === 'https:';
        const apiHttpsPort = config.injectedApiHttpsPort !== '${API_HTTPS_PORT}' && config.injectedApiHttpsPort 
            ? config.injectedApiHttpsPort 
            : null;
        const apiHttpPort = config.injectedApiPort !== '${API_PORT}' 
            ? config.injectedApiPort 
            : window.location.port || '80';
        
        // Utiliser HTTPS si disponible et page en HTTPS, sinon HTTP
        let apiUrl;
        if (isHttps && apiHttpsPort) {
            apiUrl = `https://${host}:${apiHttpsPort}`;
        } else if (apiHttpsPort) {
            // Port HTTPS configuré mais page en HTTP - essayer HTTPS quand même
            apiUrl = `https://${host}:${apiHttpsPort}`;
        } else {
            apiUrl = `http://${host}:${apiHttpPort}`;
        }
        
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
        const isHttps = window.location.protocol === 'https:';
        
        // API URL - Priorité HTTPS
        const apiHttpsPort = config.injectedApiHttpsPort !== '${API_HTTPS_PORT}' && config.injectedApiHttpsPort
            ? config.injectedApiHttpsPort : null;
        const apiHttpPort = config.injectedApiPort !== '${API_PORT}' 
            ? config.injectedApiPort : window.location.port;
        
        if (apiHttpsPort) {
            config.apiUrl = `https://${host}:${apiHttpsPort}`;
        } else {
            config.apiUrl = `http://${host}:${apiHttpPort}`;
        }
        
        // Hub URLs - Priorité HTTPS
        const hubHttpsPort = config.injectedHubHttpsPort !== '${HUB_HTTPS_PORT}' && config.injectedHubHttpsPort
            ? config.injectedHubHttpsPort : null;
        const hubApiPort = config.injectedHubApiPort !== '${HUB_API_PORT}' 
            ? config.injectedHubApiPort : '8000';
        const hubFrontendPort = config.injectedHubFrontendPort !== '${HUB_FRONTEND_PORT}' 
            ? config.injectedHubFrontendPort : '80';
        
        if (hubHttpsPort) {
            config.hubApiUrl = `https://${host}:${hubHttpsPort}`;
            config.hubFrontendUrl = `https://${host}:${hubHttpsPort}`;
        } else {
            config.hubApiUrl = `http://${host}:${hubApiPort}`;
            config.hubFrontendUrl = `http://${host}:${hubFrontendPort}`;
        }
        
        console.warn('⚠️ Utilisation des valeurs par défaut:', config);
    }
}
