# Applications distantes (hors réseau Docker du Hub)

Ce document explique comment configurer une application qui n'est **pas sur le même serveur** que le Hub.

## Table des matières

- [Prérequis](#prérequis)
- [Configuration côté Hub](#configuration-côté-hub)
- [Configuration côté Application](#configuration-côté-application)
- [Fonctionnalités supportées](#fonctionnalités-supportées)
- [Dépannage](#dépannage)

---

## Prérequis

### Côté Hub (serveur central)
1. Hub démarré et accessible depuis le réseau
2. Whitelist des IPs configurée pour accepter votre réseau

### Côté Application (serveur distant)
1. Réseau accessible vers le Hub (ports 8000/HTTP et 443/HTTPS)
2. IP fixe ou hostname résolvable

---

## Configuration côté Hub

### 1. Autoriser le réseau de l'application distante

Éditer le fichier `.env` du Hub :

```bash
# Autoriser les réseaux Docker + votre réseau local
# Format : préfixes IP séparés par des virgules
APP_WHITELIST_NETWORKS="172.,192.168.,10."
```

**Exemples selon votre réseau :**

| Réseau | Configuration |
|--------|---------------|
| Docker uniquement | `172.` (par défaut) |
| Réseau 192.168.x.x | `172.,192.168.` |
| Réseau 10.0.x.x | `172.,10.` |
| Sous-réseau précis | `172.,192.168.1.` |

### 2. Redémarrer le Hub

```bash
cd /path/to/HUB
docker compose down && docker compose up -d
```

---

## Configuration côté Application

### 1. Variables d'environnement (`.env`)

```bash
# === IDENTIFICATION ===
APP_SLUG=mon-app-distante
APP_NAME=Mon Application Distante
APP_DESCRIPTION=Application sur serveur distant

# === RÉSEAU ===
# IP ou hostname de CE serveur (visible depuis le Hub)
APP_HOST=192.168.1.100

# IP ou hostname du Hub (visible depuis ce serveur)  
HUB_HOST=192.0.2.11

# Ports du Hub
HUB_API_PORT=8000
HUB_FRONTEND_PORT=80

# === PORTS DE CETTE APPLICATION ===
API_PORT=9045
FRONTEND_PORT=4250

# === HTTPS (optionnel mais recommandé) ===
HUB_HTTPS_ENABLED=true
HUB_HTTPS_PORT=443
HUB_CA_CERT_PATH=/app/certs/hub-ca.crt
API_HTTPS_PORT=9046
FRONTEND_HTTPS_PORT=4251
```

### 2. Utiliser docker-compose.remote.yml

```bash
# Démarrage
docker compose -f docker-compose.remote.yml up -d

# Logs
docker compose -f docker-compose.remote.yml logs -f api

# Arrêt
docker compose -f docker-compose.remote.yml down
```

### 3. Différences avec docker-compose.yml standard

| Aspect | docker-compose.yml | docker-compose.remote.yml |
|--------|-------------------|---------------------------|
| Réseau Hub | Connecté via `hub_hub-network` | Pas de connexion Docker |
| Communication | Réseau Docker interne | Réseau TCP/IP externe |
| Résolution Hub | Via nom de conteneur | Via IP/hostname |
| Certificat CA | Volume partagé | Téléchargement HTTP auto |

---

## Fonctionnalités supportées

### ✅ Fonctionnent parfaitement

| Fonctionnalité | Comment ça marche |
|----------------|-------------------|
| **Auto-enregistrement** | Via IP réseau (whitelist) |
| **Authentification JWT** | Token validé via JWKS public |
| **Communication M2M** | Token `client_credentials` |
| **Backup/Restore** | Via API avec token M2M |
| **Sync Hub** | Upload/download via API |
| **Téléchargement CA** | Endpoint HTTP public |
| **HTTPS** | Avec certificat CA du Hub |

### ⚠️ Points d'attention

| Point | Explication |
|-------|-------------|
| **IP dans whitelist** | Votre IP doit correspondre à un préfixe dans `APP_WHITELIST_NETWORKS` |
| **Certificat CA** | Téléchargé automatiquement au démarrage via HTTP |
| **custom_host** | Envoyé au Hub pour qu'il connaisse votre IP |

---

## Dépannage

### Erreur : "Auto-enregistrement autorisé uniquement depuis le réseau Docker"

**Cause** : L'IP de votre serveur n'est pas dans la whitelist du Hub.

**Solution** :
1. Vérifier votre IP : `hostname -I`
2. Ajouter le préfixe dans le `.env` du Hub :
   ```bash
   APP_WHITELIST_NETWORKS="172.,192.168.,10."
   ```
3. Redémarrer le Hub

### Erreur : "Impossible de contacter le Hub"

**Causes possibles** :
1. Hub non démarré
2. Mauvaise IP/hostname dans `HUB_HOST`
3. Firewall bloquant le port
4. Mauvais port (`HUB_API_PORT`)

**Diagnostic** :
```bash
# Depuis le conteneur de l'app
docker exec mon-app-api curl -v http://HUB_HOST:8000/api/health

# Depuis l'hôte
curl -v http://192.0.2.11:8000/api/health
```

### Erreur : "certificat CA non disponible"

**Cause** : L'app n'arrive pas à télécharger le certificat CA.

**Solutions** :
1. Vérifier que le Hub est accessible en HTTP (port 8000)
2. Vérifier que la CA est initialisée : `curl http://HUB_HOST:8000/api/pki/ca.crt`
3. Copier manuellement le certificat :
   ```bash
   # Depuis le serveur Hub
   cp HUB/certs/ca/hub-ca.crt /path/to/app/certs/hub-ca.crt
   ```

### L'IP détectée est incorrecte

**Cause** : L'auto-détection IP utilise une route vers 8.8.8.8.

**Solution** : Définir explicitement `APP_HOST` dans le `.env` :
```bash
APP_HOST=192.168.1.100
```

### Vérifier la whitelist active sur le Hub

```bash
# Voir les logs du Hub lors d'une tentative d'enregistrement
docker logs hub-api 2>&1 | grep -i "whitelist\|auto-enregistrement\|IP:"
```

---

## Architecture réseau

```
┌─────────────────────────────────────────────────────────────┐
│                    RÉSEAU LOCAL 192.168.1.x                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐            ┌─────────────────────────┐ │
│  │ SERVEUR HUB     │            │ SERVEUR APPLICATION     │ │
│  │ 192.0.2.11   │◄──────────►│ 192.168.1.100           │ │
│  │                 │   TCP/IP   │                         │ │
│  │ ┌─────────────┐ │            │ ┌─────────────────────┐ │ │
│  │ │ hub-api     │ │            │ │ mon-app-api         │ │ │
│  │ │ :8000/:443  │ │            │ │ :9045/:9046         │ │ │
│  │ └─────────────┘ │            │ └─────────────────────┘ │ │
│  │ ┌─────────────┐ │            │ ┌─────────────────────┐ │ │
│  │ │hub-frontend │ │            │ │ mon-app-frontend    │ │ │
│  │ │ :80/:443    │ │            │ │ :4250/:4251         │ │ │
│  │ └─────────────┘ │            │ └─────────────────────┘ │ │
│  └─────────────────┘            └─────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Flux d'enregistrement (application distante)

```
┌──────────────┐                              ┌──────────────┐
│ App distante │                              │     Hub      │
│192.168.1.100 │                              │192.0.2.11 │
└──────┬───────┘                              └──────┬───────┘
       │                                             │
       │ 1. GET /api/pki/ca.crt (HTTP:8000)         │
       │────────────────────────────────────────────►│
       │                                             │
       │ 2. Certificat CA (PEM)                     │
       │◄────────────────────────────────────────────│
       │                                             │
       │ 3. POST /api/apps/register (HTTPS:443)     │
       │    {slug, name, custom_host: "192.168.1.100"}
       │────────────────────────────────────────────►│
       │                                      IP=192.168.1.100
       │                                      ✓ Dans whitelist
       │ 4. {client_id, client_secret}              │
       │◄────────────────────────────────────────────│
       │                                             │
       │ 5. POST /api/auth/token                    │
       │    (client_credentials)                    │
       │────────────────────────────────────────────►│
       │                                             │
       │ 6. {access_token}                          │
       │◄────────────────────────────────────────────│
       │                                             │
       │ 7. Appels API avec Bearer token            │
       │◄───────────────────────────────────────────►│
       │                                             │
```
