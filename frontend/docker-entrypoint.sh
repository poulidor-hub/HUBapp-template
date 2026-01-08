#!/bin/sh
# =============================================================================
# Entrypoint Nginx - Démarrage simple en HTTP
# =============================================================================

set -e

echo "🚀 Démarrage de Nginx (HTTP)..."

# Exécuter Nginx
exec nginx -g "daemon off;"
