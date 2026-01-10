#!/bin/bash
# ============================================================
# Script d'initialisation d'une nouvelle application HUB
# ============================================================
# Usage: ./scripts/init_new_app.sh
#        ou: bash scripts/init_new_app.sh
# ============================================================

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Trouver le répertoire du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}🚀 Initialisation d'une nouvelle application HUB${NC}"
echo ""

# Vérifier Python
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}❌ Python n'est pas installé.${NC}"
    echo "Veuillez installer Python 3.6+ pour continuer."
    exit 1
fi

# Vérifier la version de Python
PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED_VERSION="3.6"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}❌ Python $REQUIRED_VERSION ou supérieur est requis.${NC}"
    echo "Version actuelle: $PYTHON_VERSION"
    exit 1
fi

echo -e "${GREEN}✓ Python $PYTHON_VERSION détecté${NC}"
echo ""

# Lancer le script Python
cd "$PROJECT_ROOT"
$PYTHON_CMD "$SCRIPT_DIR/init_new_app.py"
