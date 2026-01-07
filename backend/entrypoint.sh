#!/bin/bash
# =============================================================================
# Entrypoint Backend - Auto-détection IP, certificats et démarrage
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
CA_CERT_PATH="${HUB_CA_CERT_PATH:-/app/certs/hub-ca.crt}"

if [ "$HUB_HTTPS_ENABLED" = "true" ]; then
    if [ -f "$CA_CERT_PATH" ] && [ -s "$CA_CERT_PATH" ]; then
        echo -e "${GREEN}🔐 Installation du certificat CA du Hub dans le système...${NC}"
        
        # Copier le certificat dans le répertoire système
        cp "$CA_CERT_PATH" /usr/local/share/ca-certificates/hub-ca.crt
        
        # Mettre à jour les certificats du système
        update-ca-certificates > /dev/null 2>&1
        
        echo -e "${GREEN}✅ Certificat CA installé avec succès${NC}"
    else
        echo -e "${YELLOW}⚠️ HTTPS activé mais certificat CA non disponible: $CA_CERT_PATH${NC}"
        echo -e "${YELLOW}   L'application va attendre le certificat au démarrage...${NC}"
    fi
fi

# === Démarrage de l'application ===
# Vérifier si les certificats SSL de l'application sont disponibles pour HTTPS
SSL_CERT="${APP_SSL_CERT_PATH:-/app/certs/server/mon-app/app.crt}"
SSL_KEY="${APP_SSL_KEY_PATH:-/app/certs/server/mon-app/app.key}"

if [ -n "$API_HTTPS_PORT" ] && [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
    echo -e "${GREEN}🔒 Certificats SSL trouvés, démarrage HTTPS sur le port 8443...${NC}"
    echo -e "${GREEN}🚀 Démarrage de l'API (HTTP:8000 + HTTPS:8443)...${NC}"
    
    # Démarrer le serveur HTTPS en arrière-plan
    uvicorn main:app --host 0.0.0.0 --port 8443 --ssl-certfile "$SSL_CERT" --ssl-keyfile "$SSL_KEY" &
    
    # Démarrer le serveur HTTP au premier plan
    exec uvicorn main:app --host 0.0.0.0 --port 8000
else
    echo -e "${GREEN}🚀 Démarrage de l'API (HTTP uniquement)...${NC}"
    exec uvicorn main:app --host 0.0.0.0 --port 8000
fi
