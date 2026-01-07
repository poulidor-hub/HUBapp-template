#!/bin/bash
# ============================================================
# Script de démarrage automatique - HUBapp_TEMPLATE
# ============================================================
# Détecte automatiquement si le réseau Hub existe et configure
# l'application en conséquence.
#
# Usage:
#   ./start.sh              # Démarrer
#   ./start.sh down         # Arrêter
#   ./start.sh logs         # Voir les logs
#   ./start.sh restart      # Redémarrer
# ============================================================

set -e

# Couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Charger les variables d'environnement depuis .env si présent
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

APP_NAME="${APP_SLUG:-mon-app}"
HUB_NETWORK="hub_hub-network"

# Fonction pour détecter si le réseau Hub existe
detect_hub_network() {
    if docker network inspect "$HUB_NETWORK" >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Réseau Hub détecté (${HUB_NETWORK})"
        export HUB_NETWORK_EXTERNAL=true
        export HUB_NETWORK_NAME="$HUB_NETWORK"
        return 0
    else
        echo -e "${YELLOW}⚠${NC} Réseau Hub non trouvé, création d'un réseau local"
        export HUB_NETWORK_EXTERNAL=false
        export HUB_NETWORK_NAME="${APP_NAME}-hub-network"
        return 1
    fi
}

# Fonction principale
main() {
    local cmd="${1:-up}"
    
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  HUBapp_TEMPLATE - ${APP_NAME}${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    case "$cmd" in
        up|start)
            detect_hub_network
            echo -e "${BLUE}▶${NC} Démarrage de l'application..."
            docker-compose up -d "${@:2}"
            echo -e "${GREEN}✓${NC} Application démarrée !"
            echo ""
            echo -e "  Frontend : http://localhost:${FRONTEND_PORT:-4250}"
            echo -e "  API      : http://localhost:${API_PORT:-9045}/api/docs"
            ;;
        down|stop)
            echo -e "${BLUE}▶${NC} Arrêt de l'application..."
            docker-compose down "${@:2}"
            echo -e "${GREEN}✓${NC} Application arrêtée"
            ;;
        restart)
            detect_hub_network
            echo -e "${BLUE}▶${NC} Redémarrage de l'application..."
            docker-compose down
            docker-compose up -d "${@:2}"
            echo -e "${GREEN}✓${NC} Application redémarrée !"
            ;;
        logs)
            docker-compose logs -f "${@:2}"
            ;;
        build)
            detect_hub_network
            echo -e "${BLUE}▶${NC} Build de l'application..."
            docker-compose build "${@:2}"
            echo -e "${GREEN}✓${NC} Build terminé"
            ;;
        status)
            detect_hub_network
            echo ""
            docker-compose ps
            ;;
        *)
            echo "Usage: $0 {up|down|restart|logs|build|status}"
            echo ""
            echo "Commandes:"
            echo "  up, start   - Démarrer l'application"
            echo "  down, stop  - Arrêter l'application"
            echo "  restart     - Redémarrer l'application"
            echo "  logs        - Afficher les logs (suivis)"
            echo "  build       - Reconstruire les images"
            echo "  status      - Afficher l'état des services"
            exit 1
            ;;
    esac
}

main "$@"
