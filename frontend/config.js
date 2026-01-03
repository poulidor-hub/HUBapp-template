/**
 * Configuration du frontend.
 * Les valeurs sont chargées dynamiquement depuis l'API.
 */

const config = {
    // Slug de l'application (doit correspondre au backend)
    appSlug: 'mon-app',
    
    // URLs - Seront mises à jour depuis /api/config
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
 * Permet de ne pas hardcoder les URLs.
 */
async function loadConfig() {
    try {
        // Déterminer l'URL de base de l'API
        // En dev: même origine, en prod: peut être différent
        const baseUrl = window.location.origin.replace(/:\d+$/, '');
        
        // Essayer plusieurs ports courants si nécessaire
        const apiPorts = [18087, 8000, 3000];
        let apiUrl = null;
        
        for (const port of apiPorts) {
            try {
                const testUrl = `${baseUrl}:${port}`;
                const response = await fetch(`${testUrl}/api/config`, { 
                    method: 'GET',
                    signal: AbortSignal.timeout(2000)
                });
                if (response.ok) {
                    apiUrl = testUrl;
                    break;
                }
            } catch (e) {
                continue;
            }
        }
        
        if (!apiUrl) {
            console.warn('API non trouvée, utilisation des valeurs par défaut');
            // Fallback sur des valeurs par défaut
            const defaultHost = window.location.hostname || '192.0.2.11';
            config.apiUrl = `http://${defaultHost}:18087`;
            config.hubApiUrl = `http://${defaultHost}:8000`;
            config.hubFrontendUrl = `http://${defaultHost}:80`;
            return;
        }
        
        const response = await fetch(`${apiUrl}/api/config`);
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
        config.apiUrl = `http://${host}:18087`;
        config.hubApiUrl = `http://${host}:8000`;
        config.hubFrontendUrl = `http://${host}:80`;
    }
}
