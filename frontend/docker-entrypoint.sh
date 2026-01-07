#!/bin/sh
# =============================================================================
# Entrypoint Nginx avec support HTTPS automatique
# =============================================================================
# Ce script détecte la présence de certificats SSL et configure Nginx en
# conséquence.
#
# Si /etc/nginx/ssl/app.crt existe → Mode HTTPS (443 + redirection 80)
# Sinon → Mode HTTP (80 uniquement)
# =============================================================================

set -e

SSL_CERT="/etc/nginx/ssl/app.crt"
SSL_KEY="/etc/nginx/ssl/app.key"

echo "🔍 Vérification de la configuration SSL..."

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
    echo "   1. cd /chemin/vers/HUB && python pki.py cert create ${APP_SLUG:-mon-app}"
    echo "   2. Copiez les certificats dans certs/server/${APP_SLUG:-mon-app}/"
    echo "   3. Redémarrez le conteneur frontend"
fi

echo ""
echo "🚀 Démarrage de Nginx..."

# Exécuter Nginx
exec nginx -g "daemon off;"
