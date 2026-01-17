# Changelog - HUBapp Template

Historique des modifications du template d'application Hub.

Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

---

## [1.9.0] - 17 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Résilience du cache JWKS pour authentification Hub
Correction d'un problème critique : lorsque le Hub SSO ne répond pas après l'expiration du token JWT, l'authentification échouait complètement.

**Problème identifié :**
- La clé publique JWKS était stockée uniquement en mémoire
- Pas de TTL sur le cache mémoire (jamais rafraîchi)
- Aucun fallback si le Hub était indisponible

**Solution implémentée :**

1. **Persistance sur disque** (`hub_auth.py`)
   - Nouvelle fonction `_save_key_to_persistent_cache()` : sauvegarde la clé publique dans `storage/hub_jwks_cache.json`
   - Nouvelle fonction `_load_key_from_persistent_cache()` : charge la clé depuis le disque avec validation d'âge (max 7 jours)

2. **Cache mémoire avec TTL**
   - Ajout de `_cached_key_fetched_at` pour suivre l'âge du cache
   - TTL de 30 minutes (`JWKS_CACHE_TTL = 1800`)
   - Fonction `_is_cache_expired()` pour vérifier la validité

3. **Fallback en cascade dans `decode_token()`**
   - Tentative de récupération depuis le Hub
   - Si échec → utilise le cache mémoire (même expiré)
   - Si pas de cache mémoire → charge depuis le cache persistant
   - Erreur 503 seulement si aucun fallback disponible

4. **Résilience dans `verify_hub_token()`**
   - Si le client JWKS échoue (Hub down), utilise automatiquement le fallback
   - Retourne HTTP 503 au lieu de 401 si le Hub est down ET pas de cache

5. **Nouveaux endpoints de diagnostic** (`main.py`)
   - `GET /api/health/hub/jwks` : statut du cache JWKS (mémoire + disque)
   - `POST /api/health/hub/jwks/refresh` : force le rafraîchissement du cache

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `backend/hub_auth.py` | Logique de persistance et fallback en cascade |
| `backend/main.py` | Endpoints de diagnostic JWKS, intégration statut cache |
| `VERSION` | Mise à jour vers 1.9.0 |
| `CHANGELOG.md` | Documentation des changements |

### 🔧 Comportement

Le système suit maintenant cette stratégie de fallback :
```
Hub JWKS (30 min cache) → Cache mémoire → Cache disque (7 jours) → Clé PEM → Erreur 503
```

### 📋 Nouveaux endpoints

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/health/hub/jwks` | GET | Statut détaillé du cache JWKS |
| `/api/health/hub/jwks/refresh` | POST | Force le rafraîchissement du cache |

---

## [1.6.0] - 4 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Système de versionnage automatique
- **Nouveau** : Fichier `VERSION` comme source unique de vérité
- **Nouveau** : Script `scripts/bump_version.py` pour synchroniser les versions
- **Nouveau** : Endpoint `GET /api/version` pour consulter la version de l'API
- **Nouveau** : Labels de version dans les images Docker
- **Nouveau** : Hook Git `pre-commit` pour synchronisation automatique à chaque commit
- **Nouveau** : Script `scripts/install-hooks.sh` pour installer les hooks Git

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `VERSION` | Nouveau fichier contenant le numéro de version |
| `scripts/bump_version.py` | Script de gestion de version automatique |
| `scripts/install-hooks.sh` | Script d'installation des hooks Git |
| `scripts/git-hooks/pre-commit` | Hook de synchronisation automatique |
| `backend/config.py` | Ajout de `APP_VERSION` lu depuis VERSION |
| `backend/main.py` | Import de `APP_VERSION`, nouvel endpoint `/api/version` |
| `frontend/package.json` | Synchronisation version 1.0.0 -> 1.6.0 |
| `Dockerfile.backend` | Ajout ARG/LABEL version, copie de VERSION |
| `Dockerfile.frontend` | Ajout ARG/LABEL version |
| `docker-compose.yml` | Ajout ARG `APP_VERSION` dans les builds |
| `README.md` | Documentation du système de versionnage |
| `CHANGELOG.md` | Ajout format Keep a Changelog |

### 🔧 Installation (une seule fois après clone)

```bash
# Installer les hooks Git pour synchronisation automatique
./scripts/install-hooks.sh
```

### 📋 Checklist pour agents IA

- [ ] Utiliser `/api/version` pour vérifier la version déployée
- [ ] Les versions se synchronisent automatiquement au commit
- [ ] Mettre à jour le CHANGELOG.md avant chaque release

---

## [1.5.0] - 3 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Système de documentation API
- **Nouveau** : Endpoints de documentation avec changelog intégré
- **Nouveau** : `GET /api/docs/changelog` - Consulter le changelog complet
- **Nouveau** : `GET /api/docs/changelog/versions` - Liste des versions disponibles
- **Nouveau** : `GET /api/docs/changelog/{version}` - Détail d'une version spécifique
- **Nouveau** : Fichier `docs/API.md` - Documentation complète de l'API

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `backend/routes/docs.py` | Nouveau routeur pour les endpoints de documentation |
| `backend/main.py` | Inclusion du routeur docs |
| `docs/API.md` | Documentation API complète |
| `CHANGELOG.md` | Nouveau fichier de changelog |

### 📋 Checklist pour agents IA

- [ ] Utiliser `/api/docs/changelog/versions` pour lister les versions
- [ ] Consulter `/api/docs/changelog/{version}` pour les détails d'une version

---

## [1.4.0] - 3 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Communication M2M renforcée
- **Amélioration** : Meilleure gestion des tokens M2M avec le Hub
- **Nouveau** : Endpoint `GET /api/m2m/status` pour vérifier la connexion M2M
- **Nouveau** : Endpoint `POST /api/m2m/test-call` pour tester les appels inter-services

### 🔧 Modifications code

| Fichier | Modification |
|---------|--------------|
| `backend/hub_client.py` | Gestion améliorée du cache de tokens |
| `backend/main.py` | Ajout endpoints M2M |

### 📋 Checklist pour agents IA

- [ ] Vérifier le statut M2M avec `/api/m2m/status`
- [ ] Utiliser le token M2M pour les appels inter-services

---

## [1.3.0] - 2 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Gestion des préférences utilisateur
- **Nouveau** : Endpoint `GET /api/preferences` pour récupérer les préférences
- **Nouveau** : Endpoint `PUT /api/preferences` pour mettre à jour les préférences
- **Nouveau** : Modèle `UserPreference` en base de données

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `backend/models.py` | Ajout modèle UserPreference |
| `backend/schemas.py` | Schémas Pydantic pour les préférences |
| `backend/main.py` | Endpoints préférences |

### 📋 Options de préférences

| Préférence | Type | Valeurs | Défaut |
|------------|------|---------|--------|
| `theme` | string | light, dark, system | system |
| `language` | string | Code langue (2-5 car.) | fr |
| `items_per_page` | int | 5-100 | 20 |
| `email_notifications` | bool | true/false | true |

---

## [1.2.0] - 2 janvier 2026

### ✨ Nouvelles fonctionnalités

#### CRUD Items complet
- **Nouveau** : `GET /api/items` - Liste paginée des items
- **Nouveau** : `POST /api/items` - Création d'item
- **Nouveau** : `GET /api/items/{id}` - Lecture d'un item
- **Nouveau** : `PUT /api/items/{id}` - Modification d'un item
- **Nouveau** : `DELETE /api/items/{id}` - Suppression d'un item

### 🔧 Modifications code

| Fichier | Modification |
|---------|--------------|
| `backend/models.py` | Modèle Item avec owner et timestamps |
| `backend/schemas.py` | Schémas ItemCreate, ItemUpdate, ItemResponse |
| `backend/main.py` | Endpoints CRUD avec pagination |

### 📋 Règles d'accès aux items

| Authentification | Accès |
|------------------|-------|
| Aucune | Items publics uniquement |
| User | Items publics + ses propres items |
| Admin | Tous les items |

---

## [1.1.0] - 1 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Système de rôles hiérarchiques
- **Nouveau** : Hiérarchie des rôles : `admin > manager > user > viewer`
- **Nouveau** : Endpoints protégés par rôle
- **Nouveau** : Support des Service Accounts

### 📝 Endpoints par rôle

| Endpoint | Rôles autorisés |
|----------|-----------------|
| `/api/viewer-only` | viewer, user, manager, admin |
| `/api/user-only` | user, manager, admin |
| `/api/manager-only` | manager, admin |
| `/api/admin-only` | admin |
| `/api/service-only` | Service Accounts uniquement |

### 🔧 Modifications code

| Fichier | Modification |
|---------|--------------|
| `backend/hub_auth.py` | Décorateurs require_role, require_any_role |
| `backend/hub_auth.py` | Fonction require_service_account |
| `backend/main.py` | Endpoints protégés par rôle |

---

## [1.0.0] - 1 janvier 2026

### 🎉 Version initiale

#### Structure du projet
- **Backend** : API FastAPI avec authentification Hub
- **Frontend** : Interface HTML/JS simple avec gestion des tokens
- **Docker** : Configuration Docker Compose pour déploiement

### 📁 Fichiers créés

| Fichier | Description |
|---------|-------------|
| `backend/main.py` | Application FastAPI principale |
| `backend/config.py` | Configuration centralisée |
| `backend/database.py` | Gestion base de données async |
| `backend/models.py` | Modèles SQLAlchemy |
| `backend/schemas.py` | Schémas Pydantic |
| `backend/hub_auth.py` | Authentification Hub JWT |
| `backend/hub_client.py` | Client Hub pour M2M |
| `frontend/index.html` | Interface utilisateur |
| `frontend/auth.js` | Gestion authentification côté client |
| `frontend/config.js` | Configuration frontend |

### 🔐 Authentification

- Validation JWT via clé publique du Hub
- Support tokens utilisateur et service account
- Auto-enregistrement auprès du Hub

### 📋 Endpoints de base

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/config` | Configuration publique |
| `GET /api/public` | Endpoint public |
| `GET /api/protected` | Endpoint authentifié |
| `GET /api/me` | Informations utilisateur |

---

## Format du changelog

Chaque entrée contient :

```markdown
## [VERSION] - DATE

### ✨ Nouvelles fonctionnalités
### 📝 Modifications
### 🔧 Modifications code
### 🗄️ Modifications base de données
### 🔒 Sécurité
### 🐛 Corrections
### ⚠️ Breaking changes
### 📋 Checklist pour agents IA
```

---

## Comment utiliser ce changelog

### Via l'API

```bash
# Voir tout le changelog
curl http://localhost:8000/api/docs/changelog

# Liste des versions
curl http://localhost:8000/api/docs/changelog/versions

# Détail d'une version
curl http://localhost:8000/api/docs/changelog/1.5.0
```

### Format des réponses

L'endpoint `/versions` retourne :
```json
{
  "total_versions": 6,
  "latest_version": "1.5.0",
  "versions": [
    {"version": "1.5.0", "date": "3 janvier 2026"},
    ...
  ]
}
```
