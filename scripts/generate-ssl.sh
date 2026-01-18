#!/bin/bash
# ============================================================
# Génération de certificats SSL auto-signés pour développement
# ============================================================
# Usage: ./scripts/generate-ssl.sh [--force]
# 
# Génère un certificat auto-signé valide 365 jours
# Couvre localhost + l'IP locale détectée + sous-réseaux courants
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$PROJECT_ROOT/ssl"

mkdir -p "$SSL_DIR"

# Vérifier si les certificats existent déjà (sauf si --force)
if [ -f "$SSL_DIR/server.crt" ] && [ -f "$SSL_DIR/server.key" ] && [ "$1" != "--force" ]; then
    echo "✅ Certificats SSL déjà présents"
    exit 0
fi

echo "🔐 Génération des certificats SSL..."

# Déterminer l'IP de l'hôte
HOST_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "192.168.1.1")
SUBNET=$(echo "$HOST_IP" | cut -d'.' -f1-3)
echo "   IP: $HOST_IP (sous-réseau $SUBNET.x)"

# Créer le fichier de configuration OpenSSL
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
O = HUBapp Dev
OU = Development
CN = localhost

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
DNS.3 = *.local
DNS.4 = host.docker.internal
IP.1 = 127.0.0.1
IP.2 = $HOST_IP
EOF

# Ajouter le sous-réseau local (x.x.x.1 à x.x.x.254)
IP_COUNT=3
for d in $(seq 1 254); do
    echo "IP.$IP_COUNT = $SUBNET.$d" >> "$SSL_DIR/openssl.cnf"
    ((IP_COUNT++))
done

# Ajouter 10.0.0.x (Docker)
for d in $(seq 1 254); do
    echo "IP.$IP_COUNT = 10.0.0.$d" >> "$SSL_DIR/openssl.cnf"
    ((IP_COUNT++))
done

echo "   $((IP_COUNT - 1)) IPs couvertes"

# Générer le certificat
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/server.key" \
    -out "$SSL_DIR/server.crt" \
    -config "$SSL_DIR/openssl.cnf" \
    -extensions v3_req 2>/dev/null

chmod 644 "$SSL_DIR/server.crt"
chmod 600 "$SSL_DIR/server.key"

echo "✅ Certificats générés: $SSL_DIR/server.{crt,key}"
