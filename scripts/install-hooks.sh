#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

# =============================================================================
# Installation des hooks Git pour le projet
# =============================================================================
# Usage: ./scripts/install-hooks.sh
# =============================================================================

set -e

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Récupérer le répertoire racine du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$ROOT_DIR/.git/hooks"
CUSTOM_HOOKS_DIR="$SCRIPT_DIR/git-hooks"

echo -e "${YELLOW}📦 Installation des hooks Git...${NC}"

# Vérifier que c'est bien un repo Git
if [ ! -d "$ROOT_DIR/.git" ]; then
    echo "❌ Ce n'est pas un dépôt Git. Initialisez avec 'git init' d'abord."
    exit 1
fi

# Créer le dossier hooks s'il n'existe pas
mkdir -p "$HOOKS_DIR"

# Installer chaque hook
for hook in "$CUSTOM_HOOKS_DIR"/*; do
    if [ -f "$hook" ]; then
        hook_name=$(basename "$hook")
        cp "$hook" "$HOOKS_DIR/$hook_name"
        chmod +x "$HOOKS_DIR/$hook_name"
        echo -e "${GREEN}  ✅ Hook '$hook_name' installé${NC}"
    fi
done

echo -e "${GREEN}✅ Hooks Git installés avec succès !${NC}"
echo ""
echo "Les versions seront maintenant synchronisées automatiquement à chaque commit."
