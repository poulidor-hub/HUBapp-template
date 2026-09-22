---
name: hub-notifications
description: Use when working with Hub notifications from an app — sending messages to users via M2M, receiving real-time SSE events, displaying MessageBanner/MessageArchive in the frontend, testing the notification circuit, or retrofitting the messaging system into a legacy app that already has M2M. Triggers on: "notification", "envoyer une notification", "message utilisateur", "send_user_message", "MessageBanner", "SSE", "notif M2M", "alerte utilisateur", "rétrofit messagerie", "intégrer messages Hub".
argument-hint: 'What notification operation is needed (send a message to users, integrate SSE, add MessageBanner UI, test the circuit, retrofit messaging into a legacy app)'
---

# Hub Notifications (M2M)

Système de notifications app→utilisateur via le Hub. Une app envoie des messages via son Service Account, le Hub les stocke et les pousse en temps réel (SSE) vers les utilisateurs connectés. Le frontend React affiche les notifications via `MessageBanner` et `MessageArchive`.

Documentation complète : `docs/HUB_MESSAGES.md`, `../../HUB_base/exemple-app.md`.

## Checklist

| Phase | Objectif | Couche |
|-------|----------|--------|
| **A** | Envoyer une notification depuis le backend | Backend (Python) |
| **B** | Recevoir les événements SSE | Frontend (React) |
| **C** | Afficher l'UI (MessageBanner + badge) | Frontend (React) |
| **D** | Tester le circuit de bout en bout | Smoke test |

## Phase A — Backend : envoyer une notification

### API canonique

```python
from backend.hub_client import hub_client

result = await hub_client.send_user_message(
    target_usernames=["jean.dupont", "marie.martin"],
    title="Nouveau document partagé",
    body="Le document 'Rapport 2026' a été partagé avec vous.",
    priority="info",           # "info" | "warning" | "urgent"
    action_url="/documents/42",  # Relative → le Hub la préfixe avec ton frontend_url
    action_label="Voir le document",
)
```

### Signature complète

```python
async def send_user_message(
    self,
    target_usernames: list[str],  # Usernames Hub (liste, min 1)
    title: str,                    # Max 200 caractères
    body: Optional[str] = None,
    priority: str = "info",        # "info" | "warning" | "urgent"
    action_url: Optional[str] = None,      # Relative (préfixée auto) ou absolue
    action_label: Optional[str] = None,    # Max 100 caractères
    expires_at: Optional[str] = None,      # ISO 8601
    is_resend: bool = False,
    original_hub_message_id: Optional[int] = None,
) -> Optional[dict]:
```

### Ce qui se passe côté Hub

1. `send_user_message` appelle `POST /api/messages/m2m/send` (auth SA + header `X-Slug`, code dans `../../HUB_base/hub/app/routes/messages.py`).
2. Le Hub crée un `UserMessage` **par destinataire**.
3. Pour chaque destinataire connecté, un événement SSE `user_message` est poussé (avec le payload `MessageBrief`).
4. Un broadcast `messages_updated` est émis à tous les connectés.

### Action URL relatives

Une URL relative (ex: `/factures/1234`) est **automatiquement préfixée** par le `frontend_url` de l'app expéditrice (ex: `http://192.0.2.11:4250/factures/1234`). Une URL absolue est conservée telle quelle. Le résultat est tronqué à 500 caractères.

### Exemple réel — exemple-app

```python
# Exemple réel — APPS/exemple-app/backend/routes/transfers.py
await hub_client.send_user_message(
    target_usernames=[transfer.owner],
    title="Document récupéré",
    body=f"{downloader_username} a téléchargé '{transfer.title}' "
         f"({transfer.file_count} fichier(s), {size}).",
    priority="info",
    action_url=f"/?transfer={transfer.id}",
    action_label="Voir le suivi",
)
```

### Gestion d'erreur

Les erreurs d'envoi ne doivent pas faire échouer le flux métier principal. Logger en warning et continuer :

```python
try:
    await hub_client.send_user_message(...)
except Exception as e:
    logger.warning(f"Échec d'envoi de notification: {e}")
    # Ne pas re-raiser — la notification est un bonus, pas une obligation
```

### Renvoi de message

Pour renvoyer un message existant :

```python
await hub_client.send_user_message(
    target_usernames=[...],
    title="Mon message",
    is_resend=True,
    original_hub_message_id=42,  # ID du message original sur le Hub
)
```

Le titre sera automatiquement préfixé avec `[Renvoi]` par le Hub.

## Phase B — Frontend : recevoir les événements SSE

### Connexion au flux

Le frontend React utilise `EventSource` natif pour se connecter au flux SSE du Hub :

```js
// Dans AuthContext.jsx (hors TanStack Query)
const streamUrl = `${hubApiUrl}/api/events/stream?token=${encodeURIComponent(jwt)}`;
const eventSource = new EventSource(streamUrl);
```

**Point critique** : `EventSource` ne supporte pas les headers HTTP → le token JWT doit être passé en **query string `?token=`**. Ne jamais tenter de le passer dans `Authorization: Bearer`.

### Proxy nginx `/hub/`

En mode production, le frontend est servi par nginx qui reverse-proxie `/hub/` vers le Hub. Le `hubApiUrl` doit être adapté :

```js
// En prod (nginx) : même origine, proxy /hub/
const hubApiUrl = `${window.location.origin}/hub`;

// En dev Vite : URL directe du Hub
const hubApiUrl = `http://${HUB_HOST}:${HUB_API_PORT}`;
```

Voir `frontend/src/context/AuthContext.jsx` et la section « Côté frontend : lecture, SSE et accusés de lecture » de `docs/HUB_MESSAGES.md`.

### Événements SSE pertinents

| Événement | Payload | Quand |
|-----------|---------|-------|
| `user_message` | `MessageBrief` (id, title, body, priority, action_url, sender_app_slug, created_at) | Nouveau message pour cet utilisateur |
| `messages_updated` | `{action, count, app}` | Après tout envoi/purge/archive |
| `ping` | `{}` | Keep-alive toutes les 30s |

### Refresh proactif

Le JWT a une durée de vie de 15 minutes. Le frontend doit rafraîchir le token **2 minutes avant expiration** pour ne jamais perdre la connexion SSE. Cette logique est déjà dans le template (`AuthContext.jsx`).

## Phase C — Frontend : afficher l'UI de notifications

### Composants disponibles dans le template

| Composant | Chemin | Rôle |
|-----------|--------|------|
| `MessageBanner` | `frontend/src/components/MessageBanner.jsx` | Overlay toast en haut de l'écran pour les nouveaux messages |
| `MessageArchive` | `frontend/src/components/MessageArchive.jsx` | Historique complet des messages + badge compteur non-lus |

### Intégration typique

Dans le template, `AuthProvider` est monté dans `frontend/src/main.jsx` et `MessageBanner`/`MessageArchive` dans le `RootLayout` (`frontend/src/routes/root.jsx`) :

```jsx
// frontend/src/routes/root.jsx (RootLayout)
import MessageBanner from '../components/MessageBanner';
import MessageArchive from '../components/MessageArchive';

function RootLayout() {
  return (
    <div className="app">
      {/* ... Header, <Outlet /> ... */}
      <MessageBanner />        {/* Toast overlay */}
      <MessageArchive />       {/* Icône avec badge + drawer */}
    </div>
  );
}
```

### Requêtes API (hors TanStack Query)

Les messages utilisent `fetch` directs + `EventSource`, pas TanStack Query :

| Opération | Endpoint | Méthode |
|-----------|----------|---------|
| Messages de l'utilisateur | `/api/messages/me` | GET |
| Compteur non-lus | `/api/messages/me/unread-count` | GET |
| Marquer comme lu | `/api/messages/{id}/read` | POST |
| Marquer tous lus | `/api/messages/read-all` | POST |
| Clic sur action | `/api/messages/{id}/click` | POST |
| Flux temps réel | `/api/events/stream` | GET (SSE) |

**Attention** : le compteur dans AuthContext s'appelle `unreadMessages` mais contient **le nombre de messages non-lus**. Le nom de variable est trompeur mais c'est la convention existante. Ne pas le renommer sans adapter tous les consommateurs.

## Phase D — Tester le circuit de bout en bout

La route de smoke test est déjà présente dans chaque app générée :

```bash
# Depuis la racine de l'app
curl -X POST http://localhost:${API_PORT:-9045}/api/tests/messages/send \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_usernames": ["votre-username"]}'
```

Route : `send_test_message_endpoint()` dans `backend/routes/tests.py` (admin only). Vérifie :
1. Que `send_user_message` retourne un succès (200 du Hub).
2. Que le message apparaît dans l'UI frontend (SSE + badge).
3. Que le clic sur l'action redirige correctement.

Après la requête, faire `make logs-api` pour vérifier l'absence d'erreurs dans les logs backend.

## Anti-patterns

| Pattern | Pourquoi c'est mal | Correction |
|---------|-------------------|------------|
| Bloquer le flux métier si `send_user_message` échoue | Une notif est un bonus, pas une obligation | try/except + log warning, ne pas re-raiser |
| Passer le JWT dans `Authorization` pour EventSource | `EventSource` ne supporte pas les headers | Passer `?token=JWT` dans l'URL |
| Oublier le proxy nginx `/hub/` en prod | Mixed content + CORS | Configurer nginx avec `location /hub/` |
| Utiliser `setInterval` pour poll `/api/messages/me` | Double flux, latence, charge | Utiliser SSE + `EventSource` natif |
| Stocker `unreadMessages` dans TanStack Query | Désynchronisation avec SSE | Garder dans AuthContext (fetch directs + EventSource) |
| `action_url` absolue en dur | Casse si l'IP/port change | `action_url` relative → le Hub résout automatiquement |

## Références

| Réf | Chemin |
|-----|--------|
| Doc messages app | `docs/HUB_MESSAGES.md` |
| Spec exemple-app | `../../HUB_base/exemple-app.md` |
| Route M2M send Hub | `../../HUB_base/hub/app/routes/messages.py` |
| SSE Hub | `../../HUB_base/hub/app/routes/events.py` |
| MessageBanner | `frontend/src/components/MessageBanner.jsx` |
| MessageArchive | `frontend/src/components/MessageArchive.jsx` |
| AuthContext (SSE) | `frontend/src/context/AuthContext.jsx` |
| Smoke test route | `backend/routes/tests.py` (`send_test_message_endpoint`) |
| Exemple notifs | `../../APPS/exemple-app/backend/routes/transfers.py` |

## Annexe — Rétrofit d'une app pré-template

> ⚠️ Cas rare. Le template fournit déjà toute la messagerie montée : `MessageBanner` et `MessageArchive` sont câblés dans le `RootLayout` (`frontend/src/routes/root.jsx`), `AuthContext` gère le flux SSE et la route smoke test existe (`send_test_message_endpoint`). Cette section ne sert **que** pour une app **legacy** (pré-template, sans messagerie) qu'on veut migrer — son ancien skill dédié `hub-messages-integration` a été fusionné ici.

### Prérequis à vérifier avant tout code

- M2M enregistré et `get_m2m_token()` opérationnel (`backend/hub_client.py`).
- `/api/config` expose `hub_api_url` et `hub_frontend_url` (`backend/main.py`).
- Un `AuthContext` frontend existe (`frontend/src/context/AuthContext.jsx`).
- En mode nginx déployé, le bloc `location /hub/` doit exister avec `proxy_buffering off`, `proxy_cache off`, `proxy_read_timeout 24h` (`nginx-ssl.conf`). Voir aussi le skill `deploy-troubleshoot`.

### Composants à monter

- `frontend/src/components/MessageBanner.jsx` + `MessageArchive.jsx` dans le layout racine (`RootLayout` dans `frontend/src/routes/root.jsx`).
- CSS `message-banner*` / `message-archive*` dans `frontend/src/styles/app.css`.
- `lucide-react` présent dans `frontend/package.json` (icônes du bandeau).
- Switch `${origin}/hub` hors dev Vite via `frontend/src/config.js` + `ConfigContext.jsx`.

### À ne pas faire

- Ne pas forcer le flux messages dans `useApiQuery`/`useApiMutation` sans redesigner l'auth refresh + SSE — c'est volontairement en `fetch` direct + `EventSource` natif dans `AuthContext`.
- Ne pas appeler `/api/messages/m2m/send` depuis le frontend (M2M only, backend).
- Ne pas stocker les messages localement — le Hub est la seule source de vérité.
