---
name: hub-m2m-communication
description: Use when working with M2M inter-app communication on the HUB — service discovery, calling shared services, outbox guaranteed delivery, exposing endpoints for service accounts, or configuring IS_SHARED. Triggers on: "appeler un service", "discover", "M2M", "service account", "IS_SHARED", "outbox", "call_discovered_service", "communication inter-apps", "api partagée".
argument-hint: 'What M2M operation is needed (discover services, call a shared app, expose an endpoint to SAs, configure outbox delivery)'
---

# Hub M2M Communication

Communication Machine-to-Machine entre applications sur le Hub POULIDOR. Couvre la découverte de services, l'appel inter-app via `hub_client`, la garantie de livraison (outbox), et l'exposition d'endpoints protégés pour les Service Accounts.

Le client canonique est le singleton `hub_client` (`backend/hub_client.py`), présent dans chaque app générée. Il gère les credentials, les tokens M2M, et le discovery.

## Checklist

| Phase | Objectif | Type |
|-------|----------|------|
| **A** | Vérifier les fondations (hub_client, credentials, hub_auth) | Pré-requis |
| **B** | Découvrir les services partagés | Consommation |
| **C** | Appeler un service M2M | Consommation |
| **D** | Exposer un endpoint aux Service Accounts | Fournisseur |

## Phase A — Fondations M2M

### Hub Client

Le singleton `hub_client` est instancié au lifespan de l'app (fonction `lifespan()` dans `backend/main.py`). Il s'auto-enregistre automatiquement auprès du Hub :

```python
# backend/main.py (lifespan)
from .hub_client import hub_client
await hub_client.register()  # Appelé au démarrage
```

**Credentials** : à l'enregistrement, le Hub crée un Service Account (`client_id` + `client_secret`). Ces credentials sont stockés **en mémoire** + dans un fichier partagé entre workers `/app/storage/.hub_credentials` (mode 0600). **Ils ne sont JAMAIS dans le `.env`** — c'est le mécanisme d'auto-enregistrement v2.0.

L'instance `hub_client` expose les méthodes principales (toutes définies dans la classe `HubClient` de `backend/hub_client.py` — se référer au nom de fonction, les numéros de lignes dérivent à chaque commit) :

| Méthode | Rôle |
|---------|------|
| `register()` | Auto-enregistrement (lock fichier inter-workers) |
| `get_m2m_token()` | OAuth2 `client_credentials` + cache + refresh auto sur 401/403 |
| `discover_services(force_refresh)` | GET `/api/apps/discover`, cache 60s |
| `get_service_by_slug(slug)` | Recherche un service découvert |
| `call_discovered_service(slug, endpoint, method, **kw)` | Appel M2M avec header `X-Slug` |
| `call_discovered_service_with_guarantee(...)` | Via outbox (livraison garantie) |
| `send_user_message(...)` | Notification app→user (voir skill `hub-notifications`) |

### Hub Auth

Les rôles sont définis dans `backend/hub_auth.py` :

| Rôle | Niveau | Dépendance FastAPI |
|------|--------|--------------------|
| viewer | 1 | — |
| user | 2 | `get_current_user` |
| manager | 3 | `require_role("manager")` |
| service | 3 | `require_service_account()` |
| admin | 4 | `require_role("admin")` |

`TokenPayload.is_service_account()` (classe `TokenPayload` dans `backend/hub_auth.py`) détecte les tokens M2M (type `service_account`, rôle `service`).

## Phase B — Découvrir les services partagés

### Lister les services disponibles

```python
from backend.hub_client import hub_client

services = await hub_client.discover_services()
# Retourne Dict[str, DiscoveredService]

for slug, svc in services.items():
    print(f"{slug}: {svc.name} — {svc.api_url}")
```

`discover_services()` retourne tous les services enregistrés comme `IS_SHARED=true` sur le Hub. Le résultat est caché 60 secondes. Utiliser `force_refresh=True` pour invalider le cache.

```python
# Trouver un service spécifique
nominatim = await hub_client.get_service_by_slug("nominatim")
```

### Exposer ta propre app comme service partagé

Pour que ton app soit découvrable par les autres :

1. Dans `.env` :
   ```
   IS_SHARED=true
   ```
2. L'auto-registration transmet ce flag au Hub.
3. Les endpoints de ton app seront automatiquement accessibles à tous les Service Accounts.

Alternative programmatique (si l'app est déjà enregistrée) : utiliser l'outil MCP `hub_app_toggle_shared`.

## Phase C — Appeler un service M2M

### Appel standard

```python
from backend.hub_client import hub_client

response = await hub_client.call_discovered_service(
    slug="exemple-app",
    endpoint="/api/products/42",
    method="GET",
)
# Retourne le body JSON parsé (dict ou list)
```

Pour un POST avec payload :

```python
response = await hub_client.call_discovered_service(
    slug="exemple-app",
    endpoint="/api/products",
    method="POST",
    json={"name": "Nouveau produit", "price": 42.0},
)
```

### Ce que fait `call_discovered_service` automatiquement

1. Résout le `api_url` du service découvert.
2. Obtient un token M2M via `get_m2m_token()` (OAuth2 client_credentials, cache, refresh auto).
3. Ajoute le header `Authorization: Bearer <token>`.
4. Ajoute le header `X-Slug: <app_slug>` (identification de l'app appelante).
5. En cas de 401 : retente avec un token rafraîchi.
6. En cas de 5xx ou `RequestError` après épuisement des retries : écrit dans l'outbox pour livraison garantie.

### Exemple réel — exemple-app-16_API_v3

Appel au service de géocoding Nominatim (exemple réel : `APPS/exemple-app-16_API_v3/backend/routes/secteurs.py`) :

```python
services = await hub_client.discover_services()
if "nominatim" in services:
    result = await hub_client.call_discovered_service(
        slug="nominatim",
        endpoint="/api/search",
        method="GET",
        params={"q": address, "limit": "1"},
    )
```

### Appel avec garantie de livraison (outbox)

Pour les opérations critiques où la perte est inacceptable :

```python
response = await hub_client.call_discovered_service_with_guarantee(
    slug="factures",
    endpoint="/api/invoices",
    method="POST",
    json=invoice_payload,
)
```

Si l'appel échoue après tous les retries (HTTP ≥ 500 ou `RequestError`), le payload est persisté dans la table `outbox`. Un worker async en arrière-plan retente avec backoff exponentiel (30s × 2^n, max 10 retries, ~17h). Le worker ré-obtient des tokens M2M frais à chaque tentative via le `auth_provider` (`backend/outbox.py`).

**Attention** : l'outbox ne garantit pas l'idempotence — c'est à l'endpoint destinataire de la gérer si nécessaire.

## Phase D — Exposer un endpoint aux Service Accounts

Pour créer un endpoint accessible uniquement aux autres apps (SA) :

```python
from backend.hub_auth import require_service_account

@router.post("/api/m2m/sync")
async def m2m_sync(
    payload: SyncPayload,
    sa: dict = Depends(require_service_account),
):
    """Endpoint reservé aux Service Accounts (autres apps)."""
    sa_slug = sa.get("sub", "unknown")
    # Logique métier...
    return {"status": "ok", "caller": sa_slug}
```

`require_service_account()` (dans `backend/hub_auth.py`) vérifie `TokenPayload.is_service_account()` et lève **403** si le token ne vient pas d'un SA.

**Ne jamais exposer un endpoint M2M sans `require_service_account()`** — tout utilisateur humain connecté pourrait l'appeler.

## Phase E — Exporter le catalogue M2M (blueprint pour IA de dev)

Pour qu'une IA de dev génère/injecte des fausses données conformes aux shapes réelles :

1. Un **admin** appelle `GET /api/apps/m2m-catalog/export` sur le Hub de prod.
2. Le Hub agrège `/api/m2m/catalog` de chaque app partagée (fallback heuristique OpenAPI).
3. Le fichier JSON téléchargé est apporté sur le serveur dev/test et filé à l'IA.
4. L'IA lit les endpoints `auth_level="service"` (M2M-reachable), génère des payloads
   conformes aux schémas, et les injecte via `call_discovered_service` en dev.

L'export ne contient **aucun secret**. L'IA n'attaque jamais la prod.

| Méthode | Rôle | Réf. |
|---------|------|------|
| `GET /api/m2m/catalog` (app) | service | introspection locale |
| `GET /api/apps/m2m-catalog/export` (Hub) | admin | agrégation parc |

## Anti-patterns

| Pattern | Pourquoi c'est mal | Correction |
|---------|-------------------|------------|
| Stocker `client_id`/`client_secret` dans `.env` | Contourne l'auto-enregistrement, dérive de sécurité | Laisser `hub_client.register()` gérer |
| Appeler `discover_services()` à chaque requête | Latence inutile, spam le Hub | Utiliser le cache 60s intégré |
| Oublier le header `X-Slug` | Le Hub ne peut pas identifier l'appelant | `call_discovered_service` le met automatiquement |
| Endpoint M2M sans `require_service_account()` | N'importe quel user connecté peut l'appeler | Toujours protéger avec la dépendance SA |
| `call_discovered_service` sans try/except | Plante la requête utilisateur si le service distant est down | Gérer l'exception, dégrader ou fallback outbox |
| Utiliser `requests`/`httpx` directement | By-pass l'auth M2M, pas de X-Slug, pas de retry | Toujours passer par `hub_client` |

## Références

| Réf | Chemin |
|-----|--------|
| hub_client | `backend/hub_client.py` |
| hub_auth | `backend/hub_auth.py` |
| outbox | `backend/outbox.py` (worker de retry avec backoff exponentiel) |
| Intégration Hub (section M2M) | `../../HUB_base/INTEGRATION.md` (dépôt HUB_base du parc) |
| Exemple réel M2M | `../../APPS/exemple-app-16_API_v3/backend/routes/secteurs.py` (dépôt APPS du parc) |
| Services partagés | `../../HUB_base/INTEGRATION.md` (dépôt HUB_base du parc) |
