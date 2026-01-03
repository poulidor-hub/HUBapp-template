/**
 * Configuration du frontend.
 * Les valeurs sont chargées depuis l'API backend /api/config.
 */

const config = {
    // Slug de l'application (doit correspondre au backend)
    appSlug: 'mon-app',
    
    // URLs - Seront chargées depuis /api/config
    apiUrl: '',
    hubApiUrl: '',
    hubFrontendUrl: '',
    
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
        // Utiliser l'hostname du navigateur et le port API fixe (9808)
        const host = window.location.hostname;
        const apiPort = 9808;  // Port fixe configuré dans .env
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
        
        // Valeurs par défaut en cas d'erreur
        const host = window.location.hostname || '192.0.2.11';
        config.apiUrl = `http://${host}:9808`;
        config.hubApiUrl = `http://${host}:8000`;
        config.hubFrontendUrl = `http://${host}:80`;
        
        console.warn('⚠️ Utilisation des valeurs par défaut:', config);
    }
}
