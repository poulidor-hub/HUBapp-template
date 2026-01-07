# Déploiement d'applications Hub

Ce document explique comment déployer une application connectée au Hub, **que ce soit sur le même serveur ou sur un serveur distant**.

## Table des matières

- [Déploiement simplifié](#déploiement-simplifié)
- [Configuration côté Hub](#configuration-côté-hub)
- [Configuration côté Application](#configuration-côté-application)
- [Fonctionnalités](#fonctionnalités)
- [Dépannage](#dépannage)

---

## Déploiement simplifié

L'application est conçue pour fonctionner **automatiquement** sur n'importe quel serveur du réseau local.

### Configuration minimale

1. **Copier le `.env.example`** vers `.env`
2. **Définir l'IP du Hub** :
   ```bash
   HUB_HOST=192.0.2.11
   ```
3. **Démarrer** :
   ```bash
   docker compose up -d
   ```

C'est tout ! L'application :
- Détecte automatiquement son IP externe
- Télécharge le certificat CA du Hub
- S'enregistre auprès du Hub

### Ce qui est automatique

| Élément | Comportement |
|---------|--------------|
| **APP_HOST** | Auto-détecté (IP externe du serveur) |
| **Certificat CA** | Téléchargé depuis le Hub au démarrage |
| **Enregistrement** | Automatique via whitelist IP |
| **Token M2M** | Obtenu automatiquement |

---

## Configuration côté Hub

### Autoriser les réseaux

Le Hub utilise une whitelist d'IP pour autoriser l'auto-enregistrement.

Éditer le `.env` du Hub :

```bash
# Autoriser les réseaux locaux (par défaut)
APP_WHITELIST_NETWORKS="172.,192.,10."
```

**Exemples selon votre réseau :**

| Réseau | Configuration |
|--------|---------------|
| Docker + LAN | `172.,192.,10.` (recommandé) |
| Sous-réseau précis | `172.,192.168.1.` |
| IP spécifique | `172.,192.168.1.100` |

Après modification, redémarrer le Hub :
```bash
docker compose down && docker compose up -d
```

---

## Configuration côté Application

### Variables d'environnement (`.env`)

```bash
# === OBLIGATOIRE ===
APP_SLUG=mon-app
APP_NAME=Mon Application
APP_DESCRIPTION=Description de l'application

# === HUB ===
HUB_HOST=192.0.2.11          # IP du Hub
HUB_API_PORT=8000               # Port API du Hub (HTTP)
HUB_HTTPS_PORT=443              # Port HTTPS du Hub

# === PORTS DE CETTE APPLICATION ===
API_PORT=9045                   # Port HTTP de l'API
FRONTEND_PORT=4250              # Port HTTP du frontend
API_HTTPS_PORT=9046             # Port HTTPS de l'API (optionnel)
FRONTEND_HTTPS_PORT=4251        # Port HTTPS du frontend (optionnel)

# === HTTPS (recommandé) ===
HUB_HTTPS_ENABLED=true
HUB_CA_CERT_PATH=/app/certs/hub-ca.crt

# === DATABASE ===
POSTGRES_HOST=mon-app-postgres
POSTGRES_USER=app_user
POSTGRES_PASSWORD=changeme_secure_123
POSTGRES_DB=app_db
```

### Variables optionnelles

```bash
# Forcer l'IP (si auto-détection incorrecte)
APP_HOST=192.168.1.100

# Mode debug
DEBUG=true
```

---

## Fonctionnalités

### ✅ Fonctionnent automatiquement

| Fonctionnalité | Description |
|----------------|-------------|
| **Auto-enregistrement** | L'app s'enregistre au Hub via IP |
| **Authentification JWT** | Tokens validés via JWKS public |
| **Communication M2M** | Accès inter-applications via service accounts |
| **Backup/Restore** | Sauvegarde automatique vers le Hub |
| **HTTPS** | Certificats gérés par la PKI du Hub |
| **Découverte services** | Les apps partagées sont découvertes automatiquement |

### Architecture réseau

```
┌─────────────────────────────────────────────────────────────────┐
│                     Réseau local (192.168.1.0/24)               │
│                                                                 │
│  ┌─────────────────┐              ┌─────────────────────────┐   │
│  │   Serveur Hub   │              │   Serveur Application   │   │
│  │  192.0.2.11  │              │    192.168.1.100        │   │
│  │                 │              │                         │   │
│  │  ┌───────────┐  │◄────────────►│  ┌─────────────────┐    │   │
│  │  │  Hub API  │  │   HTTPS      │  │  mon-app-api    │    │   │
│  │  │  :8000    │  │   :443       │  │  :9045/:9046    │    │   │
│  │  └───────────┘  │              │  └─────────────────┘    │   │
│  │                 │              │                         │   │
│  │  ┌───────────┐  │              │  ┌─────────────────┐    │   │
│  │  │  Nginx    │  │              │  │  mon-app-nginx  │    │   │
│  │  │  :80/:443 │  │              │  │  :4250/:4251    │    │   │
│  │  └───────────┘  │              │  └─────────────────┘    │   │
│  └─────────────────┘              └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

L'application communique avec le Hub via son IP (`HUB_HOST`), pas via un réseau Docker partagé.

---

## Dépannage

### Erreur : "Auto-enregistrement autorisé uniquement depuis le réseau Docker"

**Cause** : L'IP de votre serveur n'est pas dans la whitelist du Hub.

**Solution** :
1. Vérifier votre IP : `hostname -I`
2. Ajouter le préfixe dans le `.env` du Hub :
   ```bash
   APP_WHITELIST_NETWORKS="172.,192.,10."
   ```
3. Redémarrer le Hub

### Erreur : "Impossible de contacter le Hub"

**Diagnostic** :
```bash
# Tester la connexion depuis le conteneur
docker exec mon-app-api curl -v http://192.0.2.11:8000/api/health

# Tester HTTPS
docker exec mon-app-api curl -v --cacert /app/certs/hub-ca.crt https://192.0.2.11/api/health
```

**Solutions** :
- Vérifier que le Hub est démarré
- Vérifier l'IP dans `HUB_HOST`
- Vérifier que les ports sont ouverts (8000, 443)

### L'IP détectée est incorrecte (172.x.x.x)

L'auto-détection devrait éviter les IPs Docker (172.x). Si ce n'est pas le cas :

**Solution** : Définir explicitement `APP_HOST` :
```bash
APP_HOST=192.168.1.100
```

### Erreur certificat CA

**Diagnostic** :
```bash
# Vérifier que le Hub fournit le certificat
curl http://192.0.2.11:8000/api/pki/ca.crt

# Vérifier dans le conteneur
docker exec mon-app-api ls -la /app/certs/
```

**Solution manuelle** (si le téléchargement échoue) :
```bash
# Copier le certificat
curl http://192.0.2.11:8000/api/pki/ca.crt > certs/hub-ca.crt
docker compose restart api
```

### Voir les logs détaillés

```bash
# Logs de l'API
docker compose logs -f api

# Logs du Hub (pour voir les enregistrements)
docker logs hub-api 2>&1 | grep -i "enregistrement\|register"
```

---

## Migration depuis l'ancienne configuration

Si vous utilisiez l'ancienne configuration avec `HUB_NETWORK_EXTERNAL` :

1. **Supprimer** ces variables du `.env` :
   ```bash
   # Supprimer :
   # HUB_NETWORK_EXTERNAL=true
   ```

2. **Supprimer** le fichier `docker-compose.remote.yml` s'il existe

3. **Utiliser** simplement :
   ```bash
   docker compose down -v
   docker compose up -d
   ```

L'application fonctionne maintenant de la même manière partout, sans configuration réseau Docker.
