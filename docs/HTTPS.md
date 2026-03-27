# Configuration HTTPS

Ce document explique comment activer HTTPS sur les applications Hub.

## Pourquoi HTTPS ?

Certaines fonctionnalités du navigateur nécessitent un **contexte sécurisé** (HTTPS) :
- Accès caméra (`navigator.mediaDevices.getUserMedia`)
- Accès microphone
- Géolocalisation
- Notifications Push

> Par défaut, HTTPS est **désactivé**. L'application fonctionne en HTTP simple.

## Architecture

```
                       HTTPS_ENABLED=true
┌─────────────────────────────────────────────────────────┐
│                     NAVIGATEUR                           │
│                                                          │
│  https://<IP>:FRONTEND_PORT+1                            │
│       │                                                  │
│       ▼                                                  │
│  ┌──────────────────────────────────────┐               │
│  │  Nginx (SSL Termination)             │               │
│  │  Port 443 → mappé FRONTEND_PORT + 1  │               │
│  └──────────┬──────────┬───────────────┘               │
│             │          │          │                      │
│          /api/*     /hub/*      /*                       │
│             │          │          │                      │
│         Backend    Hub SSO    Fichiers                   │
│         (HTTP)     (HTTP)    statiques                   │
└─────────────────────────────────────────────────────────┘
```

### Points clés

- **Nginx** = seul composant HTTPS (SSL termination)
- **Backend** = toujours HTTP (communication interne Docker)
- **Hub** = toujours HTTP (proxifié via `/hub/` pour éviter Mixed Content)
- **Port HTTPS** = `FRONTEND_PORT + 1` (calculé automatiquement)

## Activation rapide

### 1. Activer HTTPS dans `.env`

```bash
HTTPS_ENABLED=true
```

### 2. Générer les certificats et démarrer

```bash
make ssl        # Génère les certificats auto-signés
make up         # Démarre (génère aussi les certs si absents)
```

Ou en une commande :

```bash
make start      # ./start.sh : génère les certs si HTTPS + démarre
```

### 3. Accéder à l'application

```
https://<IP>:<FRONTEND_PORT + 1>
```

Exemple : `FRONTEND_PORT=4250` → accédez à `https://192.168.1.100:4251`

> Le navigateur affichera un avertissement (certificat auto-signé) — cliquez "Avancé" → "Continuer".

## Certificats SSL

### Génération automatique

Le script `scripts/generate-ssl.sh` génère un certificat auto-signé couvrant :

| SAN | Description |
|-----|-------------|
| `DNS:localhost` | Accès local |
| `DNS:host.docker.internal` | Accès depuis Docker |
| `IP:127.0.0.1` | Loopback |
| `IP:<IP détectée>` | IP réseau de la machine |

```bash
# Génère ssl/server.crt + ssl/server.key (validité 365 jours)
./scripts/generate-ssl.sh

# Forcer la regénération
./scripts/generate-ssl.sh --force
```

### Génération de secours

Si `generate-ssl.sh` n'est pas disponible, le `docker-entrypoint.sh` du frontend
génère automatiquement un certificat minimal au démarrage du container
(couvre uniquement `localhost`).

## Convention de ports

| Mode | Port | Variable |
|------|------|----------|
| HTTP | `FRONTEND_PORT` | Configuré dans `.env` |
| HTTPS | `FRONTEND_PORT + 1` | Calculé automatiquement |

Exemple : `FRONTEND_PORT=4250` → HTTP sur 4250, HTTPS sur 4251

### Synchronisation obligatoire de `.env`

Le mapping Docker HTTPS utilise `FRONTEND_HTTPS_PORT` tel qu'il est défini dans `.env`.
Après chaque changement de `FRONTEND_PORT`, resynchronisez :

```bash
make sync-env
```

Puis démarrez avec :

```bash
docker compose up -d
```

Si `FRONTEND_HTTPS_PORT` est absent ou incohérent, le frontend échoue explicitement au démarrage
pour éviter d'exposer un ancien port HTTPS par erreur.

## Proxy Hub (Mixed Content)

En HTTPS, les appels directs vers le Hub HTTP sont bloqués par le navigateur (Mixed Content).
Nginx résout ce problème en proxifiant `/hub/` :

```nginx
location /hub/ {
    proxy_pass http://<HUB_HOST>:<HUB_API_PORT>/;
    proxy_buffering off;       # Pour SSE
    proxy_read_timeout 86400s; # 24h pour SSE
}
```

Le frontend détecte automatiquement le protocole et utilise `/hub/` en mode HTTPS :

```javascript
const isHttps = window.location.protocol === 'https:';
const hubApiUrl = isHttps
  ? `${window.location.origin}/hub`   // Proxy nginx
  : `http://${hubHost}:${hubPort}`;   // Accès direct
```

## Communication M2M (Backend)

Le système M2M n'est **pas affecté** car les échanges backend ↔ Hub
restent en HTTP direct (réseau Docker interne).

## Fichiers concernés

| Fichier | Rôle |
|---------|------|
| `nginx-ssl.conf` | Config nginx HTTPS (SSL, proxies /api/ et /hub/) |
| `nginx.conf` | Config nginx HTTP (proxies /api/ et /hub/) |
| `frontend/docker-entrypoint.sh` | Choix HTTP/HTTPS selon `HTTPS_ENABLED`, auto-génération certs |
| `scripts/generate-ssl.sh` | Génération certificats (localhost + IP détectée) |
| `ssl/openssl.cnf` | Template OpenSSL (placeholder `__IP__`) |

## Troubleshooting

### Certificat non reconnu par le navigateur

Normal avec un auto-signé. Cliquez "Avancé" → "Continuer".

### Erreur 413 (upload trop gros)

Augmenter `client_max_body_size` dans `nginx-ssl.conf`.

### Mixed Content

Vérifier que `/hub/` est bien configuré dans `nginx-ssl.conf` et que le frontend
utilise le proxy en HTTPS.

### SSE ne fonctionne pas

Vérifier dans nginx :
```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 86400s;
```

### Certificats non détectés

1. Fichiers `ssl/server.crt` et `ssl/server.key` existent ?
2. Volume monté : `./ssl:/etc/nginx/ssl:ro` ?
3. `HTTPS_ENABLED=true` dans `.env` ?

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `HTTPS_ENABLED` | Activer HTTPS | `false` |
| `FRONTEND_PORT` | Port HTTP du frontend | — |
| `HUB_HOST` | IP du serveur Hub | — |
| `HUB_API_PORT` | Port API du Hub | `8000` |
