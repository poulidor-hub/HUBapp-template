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
# Ce script télécharge les certificats AVANT de démarrer uvicorn pour
# garantir que HTTPS est disponible dès le premier démarrage.
# =============================================================================

set -e

# Couleurs pour les logs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
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

# === Téléchargement et installation du certificat CA du Hub ===
CA_CERT_PATH="/app/certs/hub-ca.crt"
CA_CERT_PATH_HUB="/app/certs/hub/hub-ca.crt"

download_ca_cert() {
    local hub_url="http://${HUB_HOST}:${HUB_API_PORT:-8000}/api/pki/ca.crt"
    echo -e "${GREEN}📥 Téléchargement du certificat CA depuis ${hub_url}...${NC}"
    
    mkdir -p /app/certs/hub
    if curl -sf --retry 5 --retry-delay 2 -o "$CA_CERT_PATH_HUB" "$hub_url"; then
        if grep -q "BEGIN CERTIFICATE" "$CA_CERT_PATH_HUB"; then
            echo -e "${GREEN}✅ Certificat CA téléchargé: $CA_CERT_PATH_HUB${NC}"
            return 0
        else
            echo -e "${RED}❌ Le fichier téléchargé n'est pas un certificat valide${NC}"
            rm -f "$CA_CERT_PATH_HUB"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️ Impossible de télécharger le certificat CA (le Hub n'utilise peut-être pas PKI)${NC}"
        return 1
    fi
}

install_ca_cert() {
    local cert_file="$1"
    if [ -f "$cert_file" ] && [ -s "$cert_file" ]; then
        echo -e "${GREEN}🔐 Installation du certificat CA dans le système...${NC}"
        cp "$cert_file" /usr/local/share/ca-certificates/hub-ca.crt
        update-ca-certificates > /dev/null 2>&1
        echo -e "${GREEN}✅ Certificat CA installé avec succès${NC}"
        return 0
    fi
    return 1
}

# Essayer d'installer un CA existant, sinon télécharger
if [ -f "$CA_CERT_PATH" ] && [ -s "$CA_CERT_PATH" ]; then
    install_ca_cert "$CA_CERT_PATH"
elif [ -f "$CA_CERT_PATH_HUB" ] && [ -s "$CA_CERT_PATH_HUB" ]; then
    install_ca_cert "$CA_CERT_PATH_HUB"
elif [ -n "$HUB_HOST" ] && [ -n "$API_HTTPS_PORT" ]; then
    # HTTPS demandé mais pas de CA - télécharger depuis le Hub
    if download_ca_cert; then
        install_ca_cert "$CA_CERT_PATH_HUB"
    fi
else
    echo -e "${YELLOW}⚠️ Pas de certificat CA (mode HTTP uniquement)${NC}"
fi

# === Téléchargement des certificats de l'application ===
SSL_CERT="/app/certs/server/app.crt"
SSL_KEY="/app/certs/server/app.key"

download_app_certs() {
    local app_slug="${APP_SLUG:-mon-app}"
    local app_host="${APP_HOST:-localhost}"
    local hub_url="http://${HUB_HOST}:${HUB_API_PORT:-8000}/api/pki/app-cert/${app_slug}"
    
    echo -e "${GREEN}📥 Téléchargement des certificats de l'application depuis le Hub...${NC}"
    
    mkdir -p /app/certs/server
    
    # Télécharger le certificat
    if curl -sf --retry 5 --retry-delay 2 -o "$SSL_CERT" "${hub_url}?file=cert&ip=${app_host}"; then
        if grep -q "BEGIN CERTIFICATE" "$SSL_CERT"; then
            echo -e "${GREEN}✅ Certificat app téléchargé: $SSL_CERT${NC}"
        else
            echo -e "${RED}❌ Certificat invalide${NC}"
            rm -f "$SSL_CERT"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️ Impossible de télécharger le certificat app${NC}"
        return 1
    fi
    
    # Télécharger la clé privée
    if curl -sf --retry 5 --retry-delay 2 -o "$SSL_KEY" "${hub_url}?file=key&ip=${app_host}"; then
        if grep -q "BEGIN.*PRIVATE KEY" "$SSL_KEY"; then
            echo -e "${GREEN}✅ Clé privée app téléchargée: $SSL_KEY${NC}"
            chmod 600 "$SSL_KEY"
        else
            echo -e "${RED}❌ Clé privée invalide${NC}"
            rm -f "$SSL_KEY"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️ Impossible de télécharger la clé privée app${NC}"
        return 1
    fi
    
    return 0
}

# Si HTTPS demandé et certificats absents, les télécharger
if [ -n "$API_HTTPS_PORT" ]; then
    if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
        echo -e "${YELLOW}⚠️ Certificats SSL non trouvés, téléchargement depuis le Hub...${NC}"
        download_app_certs || echo -e "${YELLOW}⚠️ Démarrage sans HTTPS${NC}"
    fi
fi

# === Démarrage de l'application ===
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
