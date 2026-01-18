#!/bin/sh
# =============================================================================
# Entrypoint Nginx - Démarrage HTTP ou HTTPS
# =============================================================================

set -e

# Calcul du port HTTPS = FRONTEND_PORT + 1
FRONTEND_PORT="${FRONTEND_PORT:-4250}"
HTTPS_EXTERNAL_PORT=$((FRONTEND_PORT + 1))

# Config Hub (pour le proxy /hub/)
HUB_HOST="${HUB_HOST:-192.0.2.11}"
HUB_API_PORT="${HUB_API_PORT:-8000}"

echo "📦 Configuration ports: HTTP=$FRONTEND_PORT, HTTPS=$HTTPS_EXTERNAL_PORT, HUB=$HUB_HOST:$HUB_API_PORT"

# Vérifier si les certificats SSL sont présents
if [ -f "/etc/nginx/ssl/server.crt" ] && [ -f "/etc/nginx/ssl/server.key" ]; then
    echo "🔐 Certificats SSL détectés, activation de HTTPS..."
    
    # Remplacer les placeholders dans la config nginx
    sed -e "s/\${HTTPS_PORT}/$HTTPS_EXTERNAL_PORT/g" \
        -e "s/\${HUB_HOST}/$HUB_HOST/g" \
        -e "s/\${HUB_API_PORT}/$HUB_API_PORT/g" \
        /etc/nginx/nginx-ssl.conf.template > /etc/nginx/conf.d/default.conf
    
    echo "✅ Configuration HTTPS activée"
    echo "   - HTTP  : port $FRONTEND_PORT → redirige vers HTTPS"
    echo "   - HTTPS : port $HTTPS_EXTERNAL_PORT"
    echo "   - Hub proxy : /hub/ → http://$HUB_HOST:$HUB_API_PORT"
else
    echo "🚀 Pas de certificats SSL, démarrage en HTTP uniquement..."
    echo "   💡 Pour activer HTTPS, générez les certificats avec :"
    echo "      ./scripts/generate-ssl.sh"
fi

# Exécuter Nginx
exec nginx -g "daemon off;"
