#!/bin/bash
# ===========================================
# Script de démarrage de l'application
# ===========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Démarrage de l'application"
echo ""

# Vérifier que le fichier .env existe
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "⚠️  Fichier .env non trouvé!"
    if [ -f "$SCRIPT_DIR/.env.example" ]; then
        echo "   Copie de .env.example vers .env..."
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        echo "   ⚠️  Pensez à configurer les variables dans .env"
    else
        echo "   ❌ Aucun fichier .env.example disponible."
        exit 1
    fi
fi

# Charger les variables et calculer le port HTTPS
set -a
source "$SCRIPT_DIR/.env"
set +a
export FRONTEND_HTTPS_PORT=$((${FRONTEND_PORT:-4250} + 1))

# Synchroniser FRONTEND_HTTPS_PORT dans .env
if grep -q "^FRONTEND_HTTPS_PORT=" "$SCRIPT_DIR/.env" 2>/dev/null; then
    sed -i "s/^FRONTEND_HTTPS_PORT=.*/FRONTEND_HTTPS_PORT=$FRONTEND_HTTPS_PORT/" "$SCRIPT_DIR/.env"
else
    echo "" >> "$SCRIPT_DIR/.env"
    echo "FRONTEND_HTTPS_PORT=$FRONTEND_HTTPS_PORT" >> "$SCRIPT_DIR/.env"
fi

# Générer les certificats SSL si HTTPS activé
if [ "${HTTPS_ENABLED:-false}" = "true" ]; then
    echo "🔐 Vérification des certificats SSL..."
    bash "$SCRIPT_DIR/scripts/generate-ssl.sh"
    echo ""
fi

echo "🔢 Ports: HTTP=$FRONTEND_PORT, HTTPS=$FRONTEND_HTTPS_PORT, HTTPS_ENABLED=${HTTPS_ENABLED:-false}"

# Lancer Docker Compose
echo "🐳 Lancement des conteneurs Docker..."
docker compose up -d --build

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Application démarrée avec succès !"
    echo ""
    echo "📍 URLs d'accès:"
    echo "   - Frontend HTTP:  http://${APP_HOST:-localhost}:${FRONTEND_PORT}"
    if [ "${HTTPS_ENABLED:-false}" = "true" ]; then
        echo "   - Frontend HTTPS: https://${APP_HOST:-localhost}:${FRONTEND_HTTPS_PORT}"
    fi
    echo "   - API Backend:    http://${APP_HOST:-localhost}:${API_PORT}"
    echo ""
else
    echo "❌ Erreur lors du démarrage des conteneurs"
    exit 1
fi
