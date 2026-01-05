#!/bin/bash
# =============================================================================
# Entrypoint Backend - Installation du certificat CA et démarrage
# =============================================================================

set -e

# Couleurs pour les logs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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
echo -e "${GREEN}🚀 Démarrage de l'API...${NC}"
exec uvicorn main:app --host 0.0.0.0 --port 8000
