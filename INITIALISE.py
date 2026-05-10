#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lanceur racine pour l'initialisation du template HUB.

Utilisation :
    python INITIALISE.py
    python INITIALISE.py --profile docs/client-profile.example.json
    python INITIALISE.py client.json
"""
import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    target = repo_root / "ACTIONS" / "PYTHON" / "INITIALISE.py"

    if not target.exists():
        print("\033[91m"
              f"✗ Cible introuvable : {target}\n"
              "  L'initialisation a peut-être déjà été exécutée et le script s'est auto-supprimé."
              "\033[0m")
        return 1

    os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
