# Configuration HTTPS

Ce document explique comment configurer et utiliser HTTPS sur les applications Hub.

## Pourquoi HTTPS ?

Certaines fonctionnalités du navigateur nécessitent un **contexte sécurisé** (HTTPS) :
- 📷 Accès caméra (`navigator.mediaDevices.getUserMedia`)
- 🎤 Accès microphone
- 📍 Géolocalisation
- 🔔 Notifications Push

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        NAVIGATEUR                                │
│                                                                  │
│  ┌──────────────┐     HTTPS      ┌──────────────────────────┐  │
│  │  Frontend    │◄──────────────►│  Nginx (SSL Termination) │  │
│  │  React/Vite  │                │  Port: FRONTEND_PORT + 1 │  │
│  └──────────────┘                └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
            ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
            │   /api/*     │      │   /hub/*     │      │   /*         │
            │   Backend    │      │   Hub SSO    │      │   Static     │
            │   (HTTP)     │      │   (HTTP)     │      │   Files      │
            └──────────────┘      └──────────────┘      └──────────────┘
```

### Points clés

| Composant | Protocole | Port | Description |
|-----------|-----------|------|-------------|
| Frontend externe | HTTPS | `FRONTEND_PORT + 1` | Accès navigateur sécurisé |
| Frontend interne | HTTP | 80 → 443 | Nginx redirige vers HTTPS |
| Backend | HTTP | `API_PORT` | Communication interne Docker |
| Hub SSO | HTTP | 8000 | Jamais en HTTPS (proxy nginx) |

## Installation

### 1. Générer les certificats SSL

```bash
./scripts/generate-ssl.sh
```

Ce script :
- Détecte automatiquement l'IP locale
- Génère un certificat auto-signé valide 365 jours
- Couvre toutes les IPs locales (192.168.x.x, 10.0.0.x, localhost)
- Place les fichiers dans `ssl/server.crt` et `ssl/server.key`

### 2. Redémarrer les containers

```bash
docker compose down
docker compose build --no-cache frontend
docker compose up -d
```

### 3. Accéder à l'application

```
https://<IP>:<FRONTEND_PORT + 1>
```

Exemple : Si `FRONTEND_PORT=9590`, accédez à `https://192.168.1.100:9591`

## Convention de ports

| Variable | Port HTTP | Port HTTPS |
|----------|-----------|------------|
| `FRONTEND_PORT` | 9590 | 9591 (auto) |
| Formule | N | N + 1 |

Le port HTTPS est calculé automatiquement : `HTTPS_PORT = FRONTEND_PORT + 1`

## Proxy Hub (Mixed Content)

### Le problème

Quand le frontend est en HTTPS, les appels vers le Hub HTTP sont bloqués :

```
Mixed Content: The page at 'https://...' was loaded over HTTPS, 
but requested an insecure resource 'http://hub:8000/...'. 
This request has been blocked.
```

### La solution

Nginx agit comme proxy pour les appels Hub :

```nginx
location /hub/ {
    proxy_pass http://${HUB_HOST}:${HUB_API_PORT}/;
    proxy_buffering off;      # Pour SSE
    proxy_read_timeout 86400s; # 24h pour SSE
}
```

### Adaptation du frontend

**IMPORTANT** : Tous les fichiers frontend qui appellent le Hub doivent utiliser `/hub/` en mode HTTPS.

#### 1. ConfigContext.jsx (ou équivalent)

Si votre app charge la config Hub depuis le backend, le backend retourne `http://...` mais le navigateur bloque ces appels. Il faut forcer `/hub/` :

```javascript
// Dans ConfigContext.jsx ou équivalent
const data = await response.json()

// IMPORTANT: En HTTPS, utiliser le proxy /hub/ pour éviter Mixed Content
const isHttps = window.location.protocol === 'https:'
const hubApiUrl = isHttps 
  ? `${window.location.origin}/hub`  // Proxy nginx
  : (data.hub_api_url || config.hubApiUrl)
```

#### 2. AuthContext.jsx - getHubUrl()

```javascript
const getHubUrl = () => {
  // En HTTPS, utiliser le proxy nginx /hub/ pour éviter Mixed Content
  if (window.location.protocol === 'https:') {
    return `${window.location.origin}/hub`;
  }
  
  // En HTTP, accès direct au Hub
  const envUrl = import.meta.env.VITE_HUB_URL;
  if (envUrl && !envUrl.includes('localhost')) {
    return envUrl;
  }
  const hubPort = import.meta.env.VITE_HUB_PORT || '80';
  return `http://${window.location.hostname}:${hubPort}`;
};
```

#### 3. api.js - getHubApiUrl()

```javascript
const getHubApiUrl = () => {
  // En HTTPS, utiliser le proxy nginx /hub/ pour éviter Mixed Content
  if (window.location.protocol === 'https:') {
    return `${window.location.origin}/hub`;
  }
  
  // En HTTP, accès direct au Hub
  const envUrl = import.meta.env.VITE_HUB_URL;
  if (envUrl && !envUrl.includes('localhost')) {
    return envUrl;
  }
  const hubPort = import.meta.env.VITE_HUB_PORT || '80';
  return `http://${window.location.hostname}:${hubPort}`;
};
```

### Cas d'usage concernés

| Fonctionnalité | Fichier | Variable/Fonction |
|----------------|---------|-------------------|
| SSE (événements temps réel) | AuthContext.jsx | `getHubUrl()` |
| Refresh token | api.js | `getHubApiUrl()` |
| Config chargée du backend | ConfigContext.jsx | `hubApiUrl` |
| Redirection SSO | AuthContext.jsx | `HUB_URL` |

## Communication M2M (Backend)

Le système M2M n'est **pas affecté** par HTTPS car il s'exécute côté backend :

```
┌─────────────────────────────────────────────────────────────┐
│                      SERVEUR (Docker)                        │
│                                                              │
│  ┌─────────────────┐       HTTP        ┌─────────────────┐  │
│  │ Backend Python  │◄─────────────────►│    Hub SSO      │  │
│  │ (M2M Client)    │    (Direct)       │  (port 8000)    │  │
│  └─────────────────┘                   └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

- ✅ Auto-enregistrement : HTTP direct
- ✅ Token M2M : HTTP direct
- ✅ Découverte services : HTTP direct
- ✅ Appels inter-services : HTTP direct

## Fichiers de configuration

### `nginx-ssl.conf`

Configuration nginx pour HTTPS avec :
- Redirection HTTP → HTTPS
- Certificats SSL
- Proxy `/api/` vers le backend
- Proxy `/hub/` vers le Hub SSO
- `client_max_body_size 50M` pour les uploads

### `docker-entrypoint.sh`

Script d'entrée du frontend qui :
- Détecte la présence des certificats SSL
- Calcule le port HTTPS (`FRONTEND_PORT + 1`)
- Substitue les variables dans nginx-ssl.conf
- Active la configuration HTTPS ou HTTP selon le cas

### `scripts/generate-ssl.sh`

Génère les certificats auto-signés avec :
- Détection automatique de l'IP
- SAN (Subject Alternative Names) pour toutes les IPs locales
- Validité de 365 jours

## Troubleshooting

### Erreur "NET::ERR_CERT_AUTHORITY_UNTRUSTED"

C'est normal avec un certificat auto-signé. Cliquez sur "Avancé" puis "Continuer".

### Erreur 413 Request Entity Too Large

Augmentez `client_max_body_size` dans `nginx-ssl.conf` :

```nginx
client_max_body_size 50M;  # Ou plus selon vos besoins
```

### Mixed Content Block

Vérifiez que :
1. Le proxy `/hub/` est configuré dans nginx-ssl.conf
2. Le frontend utilise `/hub/` pour les appels Hub en mode HTTPS
3. Les variables `HUB_HOST` et `HUB_API_PORT` sont définies dans docker-compose.yml

### SSE ne fonctionne pas via le proxy

Vérifiez la configuration SSE dans nginx :

```nginx
location /hub/ {
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 86400s;
}
```

### Certificats non détectés

Vérifiez que :
1. Les fichiers `ssl/server.crt` et `ssl/server.key` existent
2. Le volume est monté : `./ssl:/etc/nginx/ssl:ro`
3. Les permissions sont correctes

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `FRONTEND_PORT` | Port HTTP du frontend | 9590 |
| `HUB_HOST` | IP du serveur Hub | Auto-détecté |
| `HUB_API_PORT` | Port API du Hub | 8000 |

## Résumé

| Scénario | Configuration |
|----------|---------------|
| Développement local sans scanner | HTTP suffit |
| Scanner/caméra requis | HTTPS obligatoire |
| Communication Hub | Proxy `/hub/` en HTTPS |
| Communication M2M backend | HTTP direct (non affecté) |
