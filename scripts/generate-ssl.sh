#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

# ============================================================
# Génération de certificats SSL auto-signés pour développement
# ============================================================
# Usage: ./scripts/generate-ssl.sh [--force]
#
# Génère un certificat auto-signé couvrant localhost + IP locale.
# Simple et suffisant pour le développement.
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$PROJECT_ROOT/ssl"

mkdir -p "$SSL_DIR"

# Vérifier si les certificats existent déjà (sauf si --force)
if [ -f "$SSL_DIR/server.crt" ] && [ -f "$SSL_DIR/server.key" ] && [ "$1" != "--force" ]; then
    echo "✅ Certificats SSL déjà présents (utiliser --force pour regénérer)"
    exit 0
fi

echo "🔐 Génération des certificats SSL..."

# Détecter l'IP locale
HOST_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "127.0.0.1")
echo "   IP détectée: $HOST_IP"

# Générer un openssl.cnf minimal
cat > "$SSL_DIR/openssl.cnf" << EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
C = FR
ST = France
L = Local
O = Dev
CN = localhost

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
DNS.2 = host.docker.internal
IP.1 = 127.0.0.1
IP.2 = $HOST_IP
EOF

# Générer le certificat
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/server.key" \
    -out "$SSL_DIR/server.crt" \
    -config "$SSL_DIR/openssl.cnf" \
    -extensions v3_req 2>/dev/null

chmod 644 "$SSL_DIR/server.crt"
# Clé lisible par l'uid nginx du conteneur (USER nginx, mount :ro) — l'entrypoint
# interne ne peut PAS générer le cert dans un volume read-only. Hôte mono-user
# parc : 644 assumé (cert intranet auto-signé, remplacé par la CA du HUB via cert_sync).
chmod 644 "$SSL_DIR/server.key"

echo "✅ Certificats générés: $SSL_DIR/server.{crt,key}"
echo "   Couvre: localhost, $HOST_IP"
echo "   💡 Si l'IP change, regénérez avec: $0 --force"
