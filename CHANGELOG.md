# Changelog - HUBapp Template

Historique des modifications du template d'application Hub.

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
