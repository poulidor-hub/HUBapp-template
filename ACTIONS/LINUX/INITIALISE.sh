#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

# ============================================================
# Wrapper Linux/macOS — délègue à ACTIONS/PYTHON/INITIALISE.py
# Ce fichier (et son équivalent Windows) sera supprimé par INITIALISE.py
# une fois l'initialisation terminée avec succès.
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Détecter Python 3
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "❌ Python 3 est requis. Installez-le puis relancez ce script."
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/../PYTHON/INITIALISE.py" "$@"
