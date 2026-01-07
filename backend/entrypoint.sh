#!/bin/bash
# =============================================================================
# Entrypoint Backend - Auto-détection IP, certificats et démarrage
# =============================================================================
# 
# Ce script gère le démarrage de l'API avec support HTTPS automatique.
# Les certificats peuvent être :
# - Montés via volume Docker (méthode classique)
# - Téléchargés automatiquement depuis le Hub au démarrage (méthode auto)
#
# Le code Python (hub_client.py) télécharge automatiquement les certificats
# si nécessaire, garantissant qu'ils sont toujours valides avec la CA actuelle.
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

# === Installation du certificat CA du Hub (si présent) ===
# Note: Si absent, il sera téléchargé automatiquement par Python
CA_CERT_PATH="/app/certs/hub-ca.crt"
CA_CERT_PATH_HUB="/app/certs/hub/hub-ca.crt"

# Essayer les deux emplacements possibles
if [ -f "$CA_CERT_PATH" ] && [ -s "$CA_CERT_PATH" ]; then
    echo -e "${GREEN}🔐 Installation du certificat CA du Hub dans le système...${NC}"
    cp "$CA_CERT_PATH" /usr/local/share/ca-certificates/hub-ca.crt
    update-ca-certificates > /dev/null 2>&1
    echo -e "${GREEN}✅ Certificat CA installé avec succès${NC}"
elif [ -f "$CA_CERT_PATH_HUB" ] && [ -s "$CA_CERT_PATH_HUB" ]; then
    echo -e "${GREEN}🔐 Installation du certificat CA du Hub dans le système...${NC}"
    cp "$CA_CERT_PATH_HUB" /usr/local/share/ca-certificates/hub-ca.crt
    update-ca-certificates > /dev/null 2>&1
    echo -e "${GREEN}✅ Certificat CA installé avec succès${NC}"
else
    echo -e "${YELLOW}⚠️ Certificat CA non disponible${NC}"
    echo -e "${YELLOW}   Il sera téléchargé automatiquement depuis le Hub...${NC}"
fi

# === Démarrage de l'application ===
# Les certificats de l'application sont vérifiés/téléchargés au démarrage par Python
# Si API_HTTPS_PORT est défini, on démarre les deux serveurs (HTTP + HTTPS)

SSL_CERT="/app/certs/server/app.crt"
SSL_KEY="/app/certs/server/app.key"

# Fonction pour démarrer avec HTTPS si les certificats sont disponibles
start_with_https() {
    if [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
        echo -e "${GREEN}🔒 Certificats SSL trouvés, démarrage HTTPS sur le port 8443...${NC}"
        echo -e "${GREEN}🚀 Démarrage de l'API (HTTP:8000 + HTTPS:8443)...${NC}"
        
        # Démarrer le serveur HTTPS en arrière-plan
        uvicorn main:app --host 0.0.0.0 --port 8443 --ssl-certfile "$SSL_CERT" --ssl-keyfile "$SSL_KEY" &
        
        # Démarrer le serveur HTTP au premier plan
        exec uvicorn main:app --host 0.0.0.0 --port 8000
    else
        echo -e "${YELLOW}⚠️ Certificats SSL non trouvés (attendus dans $SSL_CERT)${NC}"
        echo -e "${YELLOW}   Les certificats seront téléchargés au démarrage de l'application${NC}"
        echo -e "${GREEN}🚀 Démarrage de l'API (HTTP uniquement pour l'instant)...${NC}"
        
        # Démarrer seulement HTTP pour l'instant
        # Le serveur HTTPS sera démarré par Python après téléchargement des certs
        exec uvicorn main:app --host 0.0.0.0 --port 8000
    fi
}

if [ -n "$API_HTTPS_PORT" ]; then
    start_with_https
else
    echo -e "${GREEN}🚀 Démarrage de l'API (HTTP uniquement)...${NC}"
    exec uvicorn main:app --host 0.0.0.0 --port 8000
fi
