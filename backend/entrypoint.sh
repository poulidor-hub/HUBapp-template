#!/bin/bash
# =============================================================================
# Entrypoint Backend - Auto-détection IP et démarrage
# =============================================================================

set -e

# Couleurs pour les logs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# === Auto-détection de l'IP de l'hôte ===
# Si APP_HOST n'est pas défini, on détecte automatiquement l'IP
if [ -z "$APP_HOST" ]; then
    # Méthode 1 : Via la route par défaut (IP de sortie)
    DETECTED_IP=$(ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K\S+' || true)
    
    # Méthode 2 : Si l'IP détectée est une IP Docker (172.x), utiliser HUB_HOST
    if [ -z "$DETECTED_IP" ] || [[ "$DETECTED_IP" == 172.* ]]; then
        # Dans Docker, on utilise HUB_HOST comme fallback (même serveur)
        if [ -n "$HUB_HOST" ]; then
            export APP_HOST="$HUB_HOST"
            echo -e "${GREEN}🌐 APP_HOST auto-détecté (même serveur que Hub): $APP_HOST${NC}"
        fi
    else
        export APP_HOST="$DETECTED_IP"
        echo -e "${GREEN}🌐 APP_HOST auto-détecté: $APP_HOST${NC}"
    fi
fi

# === Démarrage de l'application ===
echo -e "${GREEN}🚀 Démarrage de l'API (HTTP)...${NC}"
exec uvicorn main:app --host 0.0.0.0 --port 8000
