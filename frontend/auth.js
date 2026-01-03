/**
 * Module d'authentification Hub.
 * Gère la connexion, déconnexion et les tokens JWT.
 */

const auth = {
    /**
     * Redirige vers le Hub pour la connexion.
     */
    login() {
        const callbackUrl = encodeURIComponent(window.location.origin + window.location.pathname);
        const hubLoginUrl = `${config.hubFrontendUrl}?callback=${callbackUrl}`;
        console.log('🔐 Redirection vers le Hub:', hubLoginUrl);
        window.location.href = hubLoginUrl;
    },

    /**
     * Déconnexion - redirige vers le Hub avec action=logout.
     */
    logout() {
        // Supprimer les tokens locaux
        localStorage.removeItem(config.storageKeys.accessToken);
        localStorage.removeItem(config.storageKeys.refreshToken);
        
        // Rediriger vers le Hub pour déconnexion complète
        const callbackUrl = encodeURIComponent(window.location.origin + window.location.pathname);
        const hubLogoutUrl = `${config.hubFrontendUrl}?action=logout&callback=${callbackUrl}`;
        console.log('🚪 Déconnexion via le Hub');
        window.location.href = hubLogoutUrl;
    },

    /**
     * Gère le callback après connexion au Hub.
     * Le Hub renvoie les tokens dans les paramètres URL.
     */
    handleCallback() {
        const urlParams = new URLSearchParams(window.location.search);
        
        // Récupérer les tokens depuis l'URL
        const accessToken = urlParams.get('token') || urlParams.get('access_token');
        const refreshToken = urlParams.get('refresh_token');
        
        if (accessToken) {
            console.log('✅ Token reçu du Hub');
            localStorage.setItem(config.storageKeys.accessToken, accessToken);
            
            if (refreshToken) {
                localStorage.setItem(config.storageKeys.refreshToken, refreshToken);
            }
            
            // Nettoyer l'URL (supprimer les paramètres de token)
            const cleanUrl = window.location.origin + window.location.pathname;
            window.history.replaceState({}, document.title, cleanUrl);
            
            return true;
        }
        
        // Vérifier s'il y a une erreur
        const error = urlParams.get('error');
        if (error) {
            console.error('❌ Erreur d\'authentification:', error);
            alert(`Erreur de connexion: ${error}`);
            
            // Nettoyer l'URL
            const cleanUrl = window.location.origin + window.location.pathname;
            window.history.replaceState({}, document.title, cleanUrl);
        }
        
        return false;
    },

    /**
     * Vérifie si l'utilisateur est authentifié.
     */
    isAuthenticated() {
        const token = this.getToken();
        if (!token) return false;
        
        // Vérifier l'expiration du token
        const decoded = this.getDecodedToken();
        if (!decoded || !decoded.exp) return false;
        
        const now = Math.floor(Date.now() / 1000);
        return decoded.exp > now;
    },

    /**
     * Récupère le token d'accès.
     */
    getToken() {
        return localStorage.getItem(config.storageKeys.accessToken);
    },

    /**
     * Récupère le refresh token.
     */
    getRefreshToken() {
        return localStorage.getItem(config.storageKeys.refreshToken);
    },

    /**
     * Décode le token JWT (sans validation côté client).
     * La validation réelle se fait côté serveur.
     */
    getDecodedToken() {
        const token = this.getToken();
        if (!token) return null;
        
        try {
            const parts = token.split('.');
            if (parts.length !== 3) return null;
            
            const payload = parts[1];
            const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
            return JSON.parse(decoded);
        } catch (error) {
            console.error('Erreur décodage token:', error);
            return null;
        }
    },

    /**
     * Retourne le rôle de l'utilisateur pour l'application courante.
     */
    getAppRole() {
        const decoded = this.getDecodedToken();
        if (!decoded || !decoded.apps) return null;
        return decoded.apps[config.appSlug] || null;
    },

    /**
     * Vérifie si l'utilisateur a au moins le rôle spécifié.
     * Hiérarchie: viewer < user < manager < admin
     */
    hasMinRole(minRole) {
        const roleHierarchy = {
            'viewer': 1,
            'user': 2,
            'manager': 3,
            'admin': 4
        };
        
        const userRole = this.getAppRole();
        if (!userRole) return false;
        
        const decoded = this.getDecodedToken();
        
        // Les admins globaux ont tous les droits
        if (decoded?.roles?.includes('admin')) return true;
        
        return (roleHierarchy[userRole] || 0) >= (roleHierarchy[minRole] || 0);
    },

    /**
     * Rafraîchit le token d'accès.
     */
    async refreshAccessToken() {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) {
            console.error('Pas de refresh token disponible');
            return false;
        }
        
        try {
            const response = await fetch(`${config.hubApiUrl}/api/auth/token/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    refresh_token: refreshToken
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                localStorage.setItem(config.storageKeys.accessToken, data.access_token);
                
                if (data.refresh_token) {
                    localStorage.setItem(config.storageKeys.refreshToken, data.refresh_token);
                }
                
                console.log('✅ Token rafraîchi');
                return true;
            } else {
                console.error('❌ Échec rafraîchissement token');
                // Token invalide, forcer la reconnexion
                this.logout();
                return false;
            }
        } catch (error) {
            console.error('❌ Erreur rafraîchissement token:', error);
            return false;
        }
    },

    /**
     * Effectue une requête authentifiée avec gestion automatique du refresh.
     */
    async fetch(url, options = {}) {
        // Ajouter le token aux headers
        const token = this.getToken();
        if (token) {
            options.headers = {
                ...options.headers,
                'Authorization': `Bearer ${token}`
            };
        }
        
        let response = await fetch(url, options);
        
        // Si 401, tenter de rafraîchir le token
        if (response.status === 401) {
            const refreshed = await this.refreshAccessToken();
            
            if (refreshed) {
                // Réessayer avec le nouveau token
                options.headers['Authorization'] = `Bearer ${this.getToken()}`;
                response = await fetch(url, options);
            }
        }
        
        return response;
    }
};

/**
 * Intercepteur fetch global pour gérer l'authentification automatiquement.
 * Usage: authFetch('/api/items') au lieu de fetch('/api/items')
 */
async function authFetch(url, options = {}) {
    return auth.fetch(url.startsWith('http') ? url : `${config.apiUrl}${url}`, options);
}
