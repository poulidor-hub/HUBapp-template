#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""
DEPRECATED — Stub de redirection.

La logique d'initialisation est désormais exposée en priorité via INITIALISE.py
à la racine, qui délègue ensuite vers ACTIONS/PYTHON/INITIALISE.py.
Ce fichier reste présent pour compatibilité avec d'anciens hooks/scripts qui
référencent encore `scripts/init_new_app.py`.

Utilisation recommandée :
    bash INITIALISE.sh        # Linux / macOS
    INITIALISE.bat           # Windows
    python INITIALISE.py     # cross-platform
"""
import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    target = repo_root / "INITIALISE.py"

    print("\033[93m"
          "⚠  scripts/init_new_app.py est déprécié.\n"
          "   Utilisez désormais : INITIALISE.py "
          "(ou INITIALISE.sh / INITIALISE.bat à la racine)."
          "\033[0m")

    if not target.exists():
        print("\033[91m"
              f"✗ Cible introuvable : {target}\n"
              "  L'initialisation a peut-être déjà été exécutée et le script s'est auto-supprimé."
              "\033[0m")
        return 1

    # Réexécuter l'init officiel avec les mêmes arguments.
    os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
