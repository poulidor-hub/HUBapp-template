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

# Variable HTTPS_ENABLED depuis le .env
HTTPS_ENABLED="${HTTPS_ENABLED:-false}"

echo "📦 Configuration: HTTP=$FRONTEND_PORT, HTTPS=$HTTPS_EXTERNAL_PORT, HUB=$HUB_HOST:$HUB_API_PORT, HTTPS_ENABLED=$HTTPS_ENABLED"

# Vérifier si HTTPS est activé ET si les certificats SSL sont présents
if [ "$HTTPS_ENABLED" = "true" ]; then
    if [ -f "/etc/nginx/ssl/server.crt" ] && [ -f "/etc/nginx/ssl/server.key" ]; then
        echo "🔐 HTTPS activé, certificats SSL détectés..."
        
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
        echo "⚠️  HTTPS_ENABLED=true mais certificats manquants !"
        echo "   💡 Générez-les avec: ./scripts/generate-ssl.sh"
        echo "   🚀 Démarrage en HTTP par défaut..."
    fi
else
    echo "🚀 HTTPS désactivé (HTTPS_ENABLED=false), démarrage en HTTP..."
fi

# Exécuter Nginx
exec nginx -g "daemon off;"
