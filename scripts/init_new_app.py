#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED — Stub de redirection.

La logique d'initialisation a été déplacée vers ACTIONS/PYTHON/INITIALISE.py.
Ce fichier reste présent pour compatibilité avec d'anciens hooks/scripts qui
référencent encore `scripts/init_new_app.py`.

Utilisation recommandée :
    bash ACTIONS/LINUX/INITIALISE.sh        # Linux / macOS
    ACTIONS\\WINDOWS\\INITIALISE.bat        # Windows
    python ACTIONS/PYTHON/INITIALISE.py     # cross-platform
"""
import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    target = repo_root / "ACTIONS" / "PYTHON" / "INITIALISE.py"

    print("\033[93m"
          "⚠  scripts/init_new_app.py est déprécié.\n"
          "   Utilisez désormais : ACTIONS/PYTHON/INITIALISE.py "
          "(ou les wrappers ACTIONS/LINUX/INITIALISE.sh / ACTIONS/WINDOWS/INITIALISE.bat)."
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
