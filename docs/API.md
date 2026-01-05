# 📚 Documentation API - HUBapp Template

![Version](https://img.shields.io/badge/version-1.6.0-blue)

![Version](https://img.shields.io/badge/version-1.6.0-blue)

![Version](https://img.shields.io/badge/version-1.6.0-blue)

![Version](https://img.shields.io/badge/version-1.6.0-blue)

Cette documentation décrit tous les endpoints de l'API REST du template HUBapp.

## 🔗 Accès à la documentation interactive

L'API propose une documentation Swagger/OpenAPI interactive :

- **Swagger UI** : `http://localhost:8000/api/docs`
- **ReDoc** : `http://localhost:8000/api/redoc`
- **OpenAPI JSON** : `http://localhost:8000/api/openapi.json`

---

## 📋 Table des matières

1. [Authentification](#authentification)
2. [Endpoints Publics](#endpoints-publics)
3. [Endpoints Protégés](#endpoints-protégés)
4. [Gestion des Rôles](#gestion-des-rôles)
5. [Items (CRUD)](#items-crud)
6. [Préférences Utilisateur](#préférences-utilisateur)
7. [Machine-to-Machine (M2M)](#machine-to-machine-m2m)
8. [Codes d'erreur](#codes-derreur)

---

## 🔐 Authentification

L'API utilise des **JWT tokens** validés par le Hub central.

### Header d'authentification

```http
Authorization: Bearer <token>
```

### Types de tokens

| Type | Description |
|------|-------------|
| `user` | Token utilisateur (obtenu via login Hub) |
| `service` | Token service account (M2M) |

### Hiérarchie des rôles

```
admin > manager > user > viewer
```

Chaque rôle hérite des permissions des rôles inférieurs.

---

## 🌐 Endpoints Publics

Ces endpoints sont accessibles **sans authentification**.

### Health Check

```http
GET /api/health
```

Vérifie que l'API est opérationnelle.

**Réponse** `200 OK`
```json
{
  "status": "healthy",
  "app": "app-slug",
  "timestamp": "2026-01-03T10:30:00.000000"
}
```

---

### Configuration Publique

```http
GET /api/config
```

Retourne la configuration publique pour le frontend.

**Réponse** `200 OK`
```json
{
  "app_slug": "myapp",
  "app_name": "Mon Application",
  "hub_frontend_url": "http://hub.example.com",
  "hub_api_url": "http://hub.example.com/api",
  "api_url": "http://localhost:8000/api"
}
```

---

### Endpoint Public

```http
GET /api/public
```

Exemple d'endpoint accessible à tous.

**Réponse** `200 OK`
```json
{
  "message": "Cet endpoint est accessible à tous",
  "authenticated": false
}
```

---

## 🔒 Endpoints Protégés

Ces endpoints nécessitent une **authentification valide**.

### Endpoint Protégé

```http
GET /api/protected
```

Accessible à tout utilisateur authentifié.

**Headers requis**
```http
Authorization: Bearer <token>
```

**Réponse** `200 OK`
```json
{
  "message": "Bienvenue ! Vous êtes authentifié.",
  "user": "username",
  "app_role": "user",
  "token_type": "user"
}
```

---

### Informations Utilisateur

```http
GET /api/me
```

Retourne les informations de l'utilisateur connecté.

**Réponse** `200 OK`
```json
{
  "username": "john.doe",
  "roles": ["hub_user", "myapp_user"],
  "app_role": "user",
  "is_service_account": false
}
```

---

## 👥 Gestion des Rôles

Endpoints accessibles selon le niveau de rôle.

### Viewer+ (lecture seule)

```http
GET /api/viewer-only
```

**Rôles autorisés** : `viewer`, `user`, `manager`, `admin`

**Réponse** `200 OK`
```json
{
  "message": "Accès viewer accordé",
  "user": "username",
  "role": "viewer",
  "level": "viewer (lecture seule)"
}
```

---

### User+ (lecture/écriture)

```http
GET /api/user-only
```

**Rôles autorisés** : `user`, `manager`, `admin`

**Réponse** `200 OK`
```json
{
  "message": "Accès user accordé",
  "user": "username",
  "role": "user",
  "level": "user (lecture/écriture)"
}
```

---

### Manager+ (gestion)

```http
GET /api/manager-only
```

**Rôles autorisés** : `manager`, `admin`

**Réponse** `200 OK`
```json
{
  "message": "Accès manager accordé",
  "user": "username",
  "role": "manager",
  "level": "manager (gestion)"
}
```

---

### Admin Only

```http
GET /api/admin-only
```

**Rôles autorisés** : `admin` uniquement

**Réponse** `200 OK`
```json
{
  "message": "Accès admin accordé",
  "user": "username",
  "role": "admin",
  "level": "admin (tous droits)"
}
```

---

### Service Account Only

```http
GET /api/service-only
```

**Réservé aux** : Service Accounts (M2M)

**Réponse** `200 OK`
```json
{
  "message": "Accès service account accordé",
  "service": "service-name",
  "token_type": "service"
}
```

---

## 📦 Items (CRUD)

Gestion des items avec base de données.

### Lister les Items

```http
GET /api/items
```

**Paramètres de requête**

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `page` | int | 1 | Numéro de page |
| `per_page` | int | 20 | Items par page (1-100) |

**Comportement selon l'authentification**
- **Sans auth** : Items publics uniquement
- **Authentifié** : Items publics + ses propres items
- **Admin** : Tous les items

**Réponse** `200 OK`
```json
{
  "items": [
    {
      "id": 1,
      "title": "Mon Item",
      "description": "Description...",
      "is_public": true,
      "owner": "john.doe",
      "created_at": "2026-01-03T10:00:00",
      "updated_at": "2026-01-03T10:00:00"
    }
  ],
  "total": 50,
  "page": 1,
  "per_page": 20,
  "pages": 3
}
```

---

### Créer un Item

```http
POST /api/items
```

**Rôle minimum** : `user`

**Corps de la requête**
```json
{
  "title": "Nouvel Item",
  "description": "Description optionnelle",
  "is_public": false
}
```

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `title` | string | ✅ | Titre (1-255 caractères) |
| `description` | string | ❌ | Description |
| `is_public` | bool | ❌ | Visible par tous (défaut: false) |

**Réponse** `201 Created`
```json
{
  "id": 42,
  "title": "Nouvel Item",
  "description": "Description optionnelle",
  "is_public": false,
  "owner": "john.doe",
  "created_at": "2026-01-03T10:30:00",
  "updated_at": "2026-01-03T10:30:00"
}
```

---

### Récupérer un Item

```http
GET /api/items/{item_id}
```

**Paramètres**

| Paramètre | Type | Description |
|-----------|------|-------------|
| `item_id` | int | ID de l'item |

**Réponse** `200 OK`
```json
{
  "id": 1,
  "title": "Mon Item",
  "description": "Description...",
  "is_public": true,
  "owner": "john.doe",
  "created_at": "2026-01-03T10:00:00",
  "updated_at": "2026-01-03T10:00:00"
}
```

**Erreurs possibles**
- `404` : Item non trouvé
- `401` : Authentification requise (item privé)
- `403` : Accès non autorisé

---

### Modifier un Item

```http
PUT /api/items/{item_id}
```

**Rôle minimum** : `user` (propriétaire ou admin)

**Corps de la requête** (tous les champs optionnels)
```json
{
  "title": "Nouveau titre",
  "description": "Nouvelle description",
  "is_public": true
}
```

**Réponse** `200 OK` : Item mis à jour

**Erreurs possibles**
- `404` : Item non trouvé
- `403` : Seul le propriétaire peut modifier

---

### Supprimer un Item

```http
DELETE /api/items/{item_id}
```

**Rôle minimum** : `user` (propriétaire ou admin)

**Réponse** `200 OK`
```json
{
  "message": "Item supprimé",
  "detail": "Item #42 supprimé avec succès"
}
```

**Erreurs possibles**
- `404` : Item non trouvé
- `403` : Seul le propriétaire peut supprimer

---

## ⚙️ Préférences Utilisateur

Gestion des préférences personnelles.

### Récupérer les Préférences

```http
GET /api/preferences
```

**Authentification** : Requise

**Réponse** `200 OK`
```json
{
  "username": "john.doe",
  "theme": "system",
  "language": "fr",
  "items_per_page": 20,
  "email_notifications": true,
  "created_at": "2026-01-03T10:00:00",
  "updated_at": "2026-01-03T10:00:00"
}
```

> **Note** : Si les préférences n'existent pas, elles sont créées avec les valeurs par défaut.

---

### Modifier les Préférences

```http
PUT /api/preferences
```

**Authentification** : Requise

**Corps de la requête** (tous les champs optionnels)
```json
{
  "theme": "dark",
  "language": "en",
  "items_per_page": 50,
  "email_notifications": false
}
```

| Champ | Type | Valeurs | Défaut |
|-------|------|---------|--------|
| `theme` | string | `light`, `dark`, `system` | `system` |
| `language` | string | Code langue (2-5 car.) | `fr` |
| `items_per_page` | int | 5-100 | 20 |
| `email_notifications` | bool | true/false | true |

**Réponse** `200 OK` : Préférences mises à jour

---

## 🤖 Machine-to-Machine (M2M)

Endpoints pour la communication inter-services.

### Statut M2M

```http
GET /api/m2m/status
```

**Authentification** : Non requise

**Réponse** `200 OK`
```json
{
  "registered": true,
  "client_id": "myapp-client-id",
  "can_get_token": true,
  "token_preview": "eyJhbGciOiJSUzI1NiJ9.EXEMPLE.PAYLOAD.EXEMPLE.SIGNATURE",
  "error": null
}
```

---

### Test d'Appel M2M

```http
POST /api/m2m/test-call
```

**Rôle requis** : `admin`

**Paramètres de requête**

| Paramètre | Type | Description |
|-----------|------|-------------|
| `target_url` | string | URL à appeler avec le token M2M |

**Réponse** `200 OK`
```json
{
  "success": true,
  "status_code": 200,
  "response": { ... }
}
```

---

## ❌ Codes d'Erreur

| Code | Signification |
|------|---------------|
| `400` | Bad Request - Données invalides |
| `401` | Unauthorized - Token manquant ou invalide |
| `403` | Forbidden - Permissions insuffisantes |
| `404` | Not Found - Ressource introuvable |
| `422` | Unprocessable Entity - Validation échouée |
| `500` | Internal Server Error - Erreur serveur |

### Format des erreurs

```json
{
  "detail": "Description de l'erreur"
}
```

Pour les erreurs de validation (422) :
```json
{
  "detail": [
    {
      "loc": ["body", "title"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## 📝 Exemples avec cURL

### Authentification

```bash
# Obtenir la config (sans auth)
curl http://localhost:8000/api/config

# Accéder à un endpoint protégé
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/me
```

### CRUD Items

```bash
# Lister les items (page 2, 10 par page)
curl "http://localhost:8000/api/items?page=2&per_page=10"

# Créer un item
curl -X POST http://localhost:8000/api/items \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Mon Item", "description": "Test", "is_public": true}'

# Modifier un item
curl -X PUT http://localhost:8000/api/items/42 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Nouveau titre"}'

# Supprimer un item
curl -X DELETE http://localhost:8000/api/items/42 \
  -H "Authorization: Bearer $TOKEN"
```

### Préférences

```bash
# Récupérer les préférences
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/preferences

# Modifier les préférences
curl -X PUT http://localhost:8000/api/preferences \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"theme": "dark", "items_per_page": 50}'
```

---

## 🔗 Ressources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [OpenAPI Specification](https://swagger.io/specification/)
- [JWT.io](https://jwt.io/) - Debugger de tokens JWT
