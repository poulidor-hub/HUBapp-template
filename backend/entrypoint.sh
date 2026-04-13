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
    
    # Méthode 2 : Si l'IP est une IP Docker interne (172.x ou réseau bridge custom),
    # utiliser HUB_HOST car l'app est sur le même serveur
    # On compare avec la gateway Docker pour détecter une IP de conteneur
    DOCKER_GATEWAY=$(ip route 2>/dev/null | grep default | awk '{print $3}' || true)
    IS_DOCKER_IP=false
    if [ -z "$DETECTED_IP" ] || [[ "$DETECTED_IP" == 172.* ]]; then
        IS_DOCKER_IP=true
    elif [ -n "$DOCKER_GATEWAY" ] && [ -n "$DETECTED_IP" ]; then
        # Si l'IP détectée est sur le même sous-réseau que la gateway Docker, c'est une IP conteneur
        DETECTED_PREFIX=$(echo "$DETECTED_IP" | cut -d. -f1-3)
        GATEWAY_PREFIX=$(echo "$DOCKER_GATEWAY" | cut -d. -f1-3)
        if [ "$DETECTED_PREFIX" = "$GATEWAY_PREFIX" ]; then
            IS_DOCKER_IP=true
        fi
    fi

    if [ "$IS_DOCKER_IP" = true ] && [ -n "$HUB_HOST" ]; then
        export APP_HOST="$HUB_HOST"
        echo -e "${GREEN}🌐 APP_HOST auto-détecté (même serveur que Hub): $APP_HOST${NC}"
    elif [ -n "$DETECTED_IP" ]; then
        export APP_HOST="$DETECTED_IP"
        echo -e "${GREEN}🌐 APP_HOST auto-détecté: $APP_HOST${NC}"
    fi
fi

# === Démarrage de l'application ===
echo -e "${GREEN}🚀 Démarrage de l'API (HTTP)...${NC}"
exec uvicorn main:app --host 0.0.0.0 --port 8000
