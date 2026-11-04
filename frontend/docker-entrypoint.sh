#!/bin/sh
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

# =============================================================================
# Entrypoint Nginx - Démarrage HTTP ou HTTPS
# =============================================================================
# HTTPS_ENABLED=true  → active HTTPS (auto-génère les certificats si absents)
# HTTPS_ENABLED=false → HTTP uniquement (opt-out explicite)
# Port HTTPS = FRONTEND_PORT + 1
# =============================================================================

set -e

FRONTEND_PORT="${FRONTEND_PORT:-4250}"
HTTPS_EXTERNAL_PORT=$((FRONTEND_PORT + 1))
FRONTEND_HTTPS_PORT="${FRONTEND_HTTPS_PORT:-$HTTPS_EXTERNAL_PORT}"
HTTPS_ENABLED="${HTTPS_ENABLED:-true}"

if [ "$FRONTEND_HTTPS_PORT" != "$HTTPS_EXTERNAL_PORT" ]; then
    echo "❌ Configuration invalide: FRONTEND_HTTPS_PORT=$FRONTEND_HTTPS_PORT, attendu=$HTTPS_EXTERNAL_PORT (FRONTEND_PORT + 1)"
    echo "   Corrigez .env puis relancez (ex: make sync-env)"
    exit 1
fi

# Hub configuration (pour le proxy /hub/)
HUB_HOST="${HUB_HOST:-localhost}"
HUB_API_PORT="${HUB_API_PORT:-8000}"

echo "📦 Config: HTTP=$FRONTEND_PORT, HTTPS=$FRONTEND_HTTPS_PORT, HTTPS_ENABLED=$HTTPS_ENABLED, HUB=$HUB_HOST:$HUB_API_PORT"

if [ "$HTTPS_ENABLED" = "true" ]; then
    # Auto-générer les certificats si absents
    if [ ! -f "/etc/nginx/ssl/server.crt" ] || [ ! -f "/etc/nginx/ssl/server.key" ]; then
        echo "🔐 Certificats absents, génération automatique..."
        HOST_IP=$(hostname -i 2>/dev/null || echo "127.0.0.1")

        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout /etc/nginx/ssl/server.key \
            -out /etc/nginx/ssl/server.crt \
            -subj "/C=FR/ST=France/L=Local/O=Dev/CN=localhost" \
            -addext "subjectAltName=DNS:localhost,DNS:host.docker.internal,IP:127.0.0.1,IP:$HOST_IP" \
            2>/dev/null

        echo "✅ Certificats auto-générés (localhost + $HOST_IP)"
    fi

    # Activer la config SSL
    sed -e "s/\${HTTPS_PORT}/$FRONTEND_HTTPS_PORT/g" \
        -e "s/\${HUB_HOST}/$HUB_HOST/g" \
        -e "s/\${HUB_API_PORT}/$HUB_API_PORT/g" \
        /etc/nginx/nginx-ssl.conf.template > /etc/nginx/conf.d/default.conf

    echo "✅ HTTPS activé"
    echo "   HTTP :80 → redirige vers HTTPS :$FRONTEND_HTTPS_PORT"
    echo "   Hub proxy: /hub/ → http://$HUB_HOST:$HUB_API_PORT"
else
    echo "🚀 Mode HTTP uniquement"
    # Substituer les variables Hub dans la config HTTP
    sed -e "s/\${HUB_HOST}/$HUB_HOST/g" \
        -e "s/\${HUB_API_PORT}/$HUB_API_PORT/g" \
        /etc/nginx/conf.d/default.conf > /tmp/nginx-http.conf \
        && mv /tmp/nginx-http.conf /etc/nginx/conf.d/default.conf
    echo "   Hub proxy: /hub/ → http://$HUB_HOST:$HUB_API_PORT"
fi

exec nginx -g "daemon off;"
