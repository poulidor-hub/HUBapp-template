#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "❌ Python 3 est requis. Installez-le puis relancez ce script."
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/INITIALISE.py" "$@"
