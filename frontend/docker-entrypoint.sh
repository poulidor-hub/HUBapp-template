#!/bin/sh
# =============================================================================
# Entrypoint Nginx avec support HTTPS automatique
# =============================================================================
# Ce script détecte la présence de certificats SSL et configure Nginx en
# conséquence. Si les certificats sont absents, il tente de les télécharger
# depuis le Hub.
#
# Si /etc/nginx/ssl/app.crt existe → Mode HTTPS (443 + redirection 80)
# Sinon → Mode HTTP (80 uniquement)
# =============================================================================

set -e

SSL_CERT="/etc/nginx/ssl/app.crt"
SSL_KEY="/etc/nginx/ssl/app.key"
APP_SLUG="${APP_SLUG:-mon-app}"

# Fonction pour télécharger les certificats depuis le Hub
download_certs() {
    if [ -z "$HUB_HOST" ]; then
        echo "⚠️  HUB_HOST non défini, impossible de télécharger les certificats"
        return 1
    fi
    
    HUB_API_PORT="${HUB_API_PORT:-8000}"
    APP_HOST="${APP_HOST:-$HUB_HOST}"
    HUB_URL="http://${HUB_HOST}:${HUB_API_PORT}/api/pki/app-cert/${APP_SLUG}"
    
    echo "📥 Téléchargement des certificats depuis le Hub..."
    
    # Créer le répertoire SSL si nécessaire
    mkdir -p /etc/nginx/ssl
    
    # Télécharger le certificat
    if wget -q -O "$SSL_CERT" "${HUB_URL}?file=cert&ip=${APP_HOST}" 2>/dev/null; then
        if grep -q "BEGIN CERTIFICATE" "$SSL_CERT" 2>/dev/null; then
            echo "✅ Certificat téléchargé: $SSL_CERT"
        else
            echo "❌ Certificat invalide"
            rm -f "$SSL_CERT"
            return 1
        fi
    else
        echo "❌ Impossible de télécharger le certificat"
        return 1
    fi
    
    # Télécharger la clé privée
    if wget -q -O "$SSL_KEY" "${HUB_URL}?file=key&ip=${APP_HOST}" 2>/dev/null; then
        if grep -q "PRIVATE KEY" "$SSL_KEY" 2>/dev/null; then
            echo "✅ Clé privée téléchargée: $SSL_KEY"
            chmod 600 "$SSL_KEY"
        else
            echo "❌ Clé privée invalide"
            rm -f "$SSL_KEY"
            return 1
        fi
    else
        echo "❌ Impossible de télécharger la clé privée"
        return 1
    fi
    
    return 0
}

echo "🔍 Vérification de la configuration SSL..."

# Si les certificats n'existent pas, essayer de les télécharger
if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
    echo "ℹ️  Certificats SSL non trouvés localement"
    if [ -n "$HUB_HOST" ]; then
        download_certs || echo "⚠️  Téléchargement des certificats échoué"
    fi
fi

if [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
    echo "✅ Certificats SSL détectés"
    echo "   📜 Certificat: $SSL_CERT"
    echo "   🔑 Clé privée: $SSL_KEY"
    
    # Copier la configuration HTTPS
    if [ -f "/etc/nginx/nginx-https.conf" ]; then
        cp /etc/nginx/nginx-https.conf /etc/nginx/conf.d/default.conf
        echo "🔒 Mode HTTPS activé (ports 80 → 443)"
    else
        echo "⚠️  Fichier nginx-https.conf manquant, mode HTTP par défaut"
    fi
else
    echo "ℹ️  Pas de certificats SSL détectés"
    echo "📡 Mode HTTP uniquement (port 80)"
    echo ""
    echo "💡 Pour activer HTTPS :"
    echo "   1. cd /chemin/vers/HUB && python pki.py cert create ${APP_SLUG}"
    echo "   2. Copiez les certificats dans certs/server/${APP_SLUG}/"
    echo "   3. Redémarrez le conteneur frontend"
fi

echo ""
echo "🚀 Démarrage de Nginx..."

# Exécuter Nginx
exec nginx -g "daemon off;"
