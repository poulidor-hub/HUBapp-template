# Analyse d'Intégration Hub - Template v2

> **Date d'analyse** : 3 janvier 2026  
> **Version de la documentation Hub** : 2.5.0  
> **Source** : `http://192.0.2.11:8000/api/docs/integration`

Ce document compare notre implémentation avec la documentation officielle du Hub v2.5.0 et identifie les écarts ou points d'attention.

---

## 1. Champ `type` vs `token_type` dans le JWT

### 📖 Ce que dit la documentation

La documentation montre que le champ dans le token JWT est **`type`**, pas `token_type` :

```json
{
  "sub": "jean.dupont",
  "roles": ["user"],
  "apps": {
    "salarie": "admin",
    "compta": "viewer"
  },
  "type": "user",    // ← "type", pas "token_type"
  "exp": 1735650600,
  "iat": 1735648800,
  "jti": "abc123"
}
```

### ⚠️ Notre implémentation

Dans `hub_auth.py`, nous lisions `payload.get("type", "user")` mais la classe `TokenPayload` avait un attribut nommé `token_type`. C'était correct mais potentiellement confus.

### 🔧 Correction appliquée

```python
# Accepter les deux noms de champs par sécurité
token_type=payload.get("type", payload.get("token_type", "user"))
```

### 📝 Recommandation pour la documentation Hub

Clarifier si le champ est `type` ou `token_type` dans le payload JWT. Les exemples montrent `type` mais certains textes mentionnent `token_type`.

---

## 2. Détection des Service Accounts

### 📖 Ce que dit la documentation

La documentation indique plusieurs façons d'identifier un service account :

1. **Token introspection** retourne `"token_type": "string"` (pas spécifié la valeur exacte)
2. **Dans les exemples de code** : `self.token_type == "service_account"`
3. **Dans la structure JWT** : `"type": "user"` ou `"type": "service_account"`
4. **Dans apps** : le rôle peut être `"service"` pour les service accounts

### ⚠️ Ambiguïté identifiée

La documentation n'est pas explicite sur :
- La valeur exacte de `type` pour un service account (`"service"` ou `"service_account"` ?)
- Si le rôle dans `apps` est toujours `"service"` pour les M2M

### 🔧 Notre implémentation (robuste)

```python
def is_service_account(self) -> bool:
    """Vérifie si c'est un service account (M2M)."""
    return (
        self.token_type in ("service", "service_account") or 
        "service_account" in self.roles or
        "service" in self.apps.values()
    )
```

### 📝 Recommandation pour la documentation Hub

Ajouter un exemple complet de token JWT pour un service account M2M.

---

## 3. Format de réponse de `/api/auth/token`

### 📖 Ce que dit la documentation

```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer",
  "expires_at": "2025-12-31T12:30:00",
  "refresh_token": "xYz123..."
}
```

### ✅ Conforme

Notre implémentation parse correctement `expires_at` en datetime.

### ⚠️ Point d'attention

Le champ `expires_at` est une **date ISO** (pas un timestamp Unix comme `exp` dans le JWT). Notre code gère les deux cas :

```python
if "expires_at" in data:
    expires_str = data["expires_at"].replace("Z", "+00:00")
    self._token_expires_at = datetime.fromisoformat(expires_str).replace(tzinfo=None)
else:
    expires_in = data.get("expires_in", 1800)
    self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
```

---

## 4. Auto-enregistrement : Champ `name` optionnel

### 📖 Ce que dit la documentation

```json
{
  "slug": "mon-app",           // REQUIS
  "name": "Mon Application",   // OPTIONNEL - utilise le slug si absent
  "api_port": 18087,           // REQUIS
  "frontend_port": 4178        // OPTIONNEL
}
```

### ✅ Conforme

Notre implémentation envoie correctement les champs optionnels :

```python
json={
    "slug": self.settings.APP_SLUG,
    "name": self.settings.APP_NAME,  # Optionnel mais envoyé
    "description": self.settings.APP_DESCRIPTION,
    "api_port": self.settings.API_PORT,
    "frontend_port": self.settings.FRONTEND_PORT,
}
```

---

## 5. Endpoints d'auto-enregistrement

### 📖 Ce que dit la documentation

| Endpoint | Header requis | Description |
|----------|---------------|-------------|
| `POST /api/apps/register` | Aucun | Auto-enregistrement |
| `GET /api/apps/me/credentials` | `X-Slug: mon-app` | Récupère infos (sans secret) |
| `POST /api/apps/me/regenerate-secret` | `X-Slug: mon-app` | Régénère le secret |

### ✅ Conforme

Notre implémentation utilise correctement le header `X-Slug` :

```python
response = await client.post(
    f"{self.settings.hub_api_url}/api/apps/me/regenerate-secret",
    headers={"X-Slug": self.settings.APP_SLUG}
)
```

---

## 6. Hiérarchie des rôles

### 📖 Ce que dit la documentation

| Rôle | Niveau | Description |
|------|--------|-------------|
| `admin` | 4 | Tous les droits |
| `manager` | 3 | Gestion des données |
| `user` | 2 | Accès standard |
| `viewer` | 1 | Lecture seule |
| `service` | 3 | Service Account (M2M) |

### ✅ Conforme

Notre `ROLE_MAPPING` correspond exactement :

```python
ROLE_MAPPING = {
    "viewer": RoleLevel.VIEWER,   # 1
    "user": RoleLevel.USER,       # 2
    "manager": RoleLevel.MANAGER, # 3
    "admin": RoleLevel.ADMIN,     # 4
    "service": RoleLevel.SERVICE, # 3
}
```

---

## 7. Endpoint JWKS

### 📖 Ce que dit la documentation

L'endpoint JWKS est : `GET /api/auth/.well-known/jwks.json`

Options de cache recommandées :
```python
PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
```

### ⚠️ Notre implémentation

Nous utilisons `PyJWKClient` sans les options de cache :

```python
self._jwk_client = PyJWKClient(jwks_url)
```

### 🔧 Amélioration suggérée

```python
self._jwk_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
```

---

## 8. Gestion du refresh token

### 📖 Ce que dit la documentation

Deux endpoints disponibles :

1. **Via `/api/auth/token`** (OAuth2 standard) :
   ```
   POST /api/auth/token
   Content-Type: application/x-www-form-urlencoded
   
   grant_type=refresh_token&refresh_token=xyz123
   ```

2. **Via `/api/auth/token/refresh`** (JSON body) :
   ```json
   POST /api/auth/token/refresh
   { "refresh_token": "xyz123" }
   ```

### ✅ Conforme

Notre frontend utilise le premier format (OAuth2 standard), ce qui est correct.

---

## 9. Paramètre `action=logout` pour le frontend

### 📖 Ce que dit la documentation

> ⚠️ **IMPORTANT** : Utiliser `action=logout` pour éviter la reconnexion automatique !

```javascript
// ✅ CORRECT
window.location.href = `${HUB_URL}?action=logout`;

// ❌ INCORRECT - cause une boucle de reconnexion
window.location.href = `${HUB_URL}?callback=${callbackUrl}`;
```

### ✅ Conforme

Notre `auth.js` implémente correctement ce comportement :

```javascript
async logout() {
    // ... révocation du token ...
    
    // ⚠️ Rediriger vers le Hub SANS callback, avec action=logout
    window.location.href = `${CONFIG.HUB_FRONTEND_URL}?action=logout`;
}
```

---

## 10. Services partagés (`is_shared_service`)

### 📖 Ce que dit la documentation (Nouveauté v2.1)

Les APIs marquées comme `is_shared_service=true` sont automatiquement accessibles par tous les nouveaux service accounts créés.

```sql
UPDATE applications SET is_shared_service = TRUE WHERE slug = 'salarie';
```

### ⚠️ Notre template

Notre template ne mentionne pas cette fonctionnalité. Si notre application doit être une API partagée (données communes), il faudra la configurer côté Hub.

### 📝 À documenter dans le README

Si votre application fournit des données partagées, demandez à un admin Hub de la marquer comme service partagé.

---

## 11. Durée des tokens

### 📖 Ce que dit la documentation

| Type | Durée | Configurable par |
|------|-------|------------------|
| Access Token | 30 minutes | Hub uniquement |
| Refresh Token | 7 jours | Hub uniquement |
| Token M2M | 30 minutes | Hub uniquement |

### ✅ Conforme

Notre code prend en compte ces durées :
- Renouvellement M2M 5 minutes avant expiration
- Pas de manipulation de durée côté application

---

## 12. Configuration réseau Docker

### 📖 Ce que dit la documentation

```yaml
networks:
  hub-network:
    external: true
    name: hub_hub-network
```

### ✅ Conforme

Notre `docker-compose.yml` utilise bien le réseau externe `hub_hub-network`.

---

## Résumé des écarts

| # | Problème | Sévérité | Statut |
|---|----------|----------|--------|
| 1 | Champ `type` vs `token_type` | 🟡 Mineur | ✅ Corrigé |
| 2 | Détection service account ambiguë | 🟡 Mineur | ✅ Robustifié |
| 3 | Format `expires_at` | 🟢 Info | ✅ OK |
| 4 | Champs optionnels register | 🟢 Info | ✅ OK |
| 5 | Header X-Slug | 🟢 Info | ✅ OK |
| 6 | Hiérarchie rôles | 🟢 Info | ✅ OK |
| 7 | Cache JWKS manquant | 🟡 Mineur | ⚠️ À améliorer |
| 8 | Refresh token | 🟢 Info | ✅ OK |
| 9 | action=logout | 🟢 Info | ✅ OK |
| 10 | Services partagés | 🟢 Info | 📝 À documenter |
| 11 | Durée tokens | 🟢 Info | ✅ OK |
| 12 | Réseau Docker | 🟢 Info | ✅ OK |

---

## Actions recommandées

### Immédiat
1. ✅ Corriger la lecture du champ `type`/`token_type`
2. ✅ Robustifier la détection des service accounts

### Optionnel (améliorations)
3. ⬜ Ajouter le cache JWKS (`cache_keys=True, lifespan=3600`)
4. ⬜ Documenter la fonctionnalité `is_shared_service` dans le README

### Pour la documentation Hub
5. ⬜ Clarifier le nom exact du champ (`type` vs `token_type`)
6. ⬜ Ajouter un exemple de token JWT pour service account
7. ⬜ Documenter les valeurs possibles de `type` (`user`, `service_account`, `service`)

---

*Analyse effectuée en comparant le code du template avec la documentation officielle du Hub v2.5.0*
