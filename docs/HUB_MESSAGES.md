# Integration du systeme de messages Hub

Ce document explique comment le template communique avec le systeme de notifications/messages du Hub, et comment retrofiter cette logique dans une ancienne application qui possede deja le socle M2M.

Le point cle est le suivant :

- l'envoi d'un message se fait cote backend, avec le service account M2M de l'application ;
- la reception, l'affichage et l'accuse de lecture se font cote frontend, avec le token utilisateur Hub.

Autrement dit, le systeme de messages du template n'est pas un simple bloc M2M. C'est un assemblage backend + frontend + proxy HTTPS.

## Resume executif

Si votre ancienne application a deja :

- l'authentification Hub cote utilisateur ;
- un client M2M capable d'obtenir un token service account ;
- un endpoint public de configuration pour le frontend ;

alors il suffit generalement d'ajouter :

1. un helper backend qui appelle l'endpoint Hub `/api/messages/m2m/send` ;
2. la logique frontend qui ecoute `/api/events/stream` et charge `/api/messages/me` ;
3. les composants d'interface de messages ;
4. le proxy `/hub/` si l'application tourne en HTTPS.

## Architecture reelle du template

Le flux complet est le suivant :

```text
Backend metier
  -> HubClient.send_user_message(...)
  -> POST Hub /api/messages/m2m/send
  -> le Hub stocke et distribue le message

Frontend utilisateur
  -> GET Hub /api/messages/me/unread-count
  -> GET Hub /api/messages/me
  -> EventSource Hub /api/events/stream
  -> affichage MessageBanner + MessageArchive
  -> POST Hub /api/messages/{id}/read
  -> POST Hub /api/messages/read-all
```

Consequences importantes :

- le template ne stocke pas les messages dans sa base locale ;
- il n'expose pas d'endpoint local `/api/messages/*` ;
- la source de verite des messages est le Hub ;
- le backend sert surtout a envoyer des messages via M2M ;
- le frontend parle directement au Hub pour lire les messages et ouvrir le flux SSE.

## Fichiers du template concernes

| Zone | Fichier | Role | Necessaire pour un retrofit legacy |
|------|---------|------|------------------------------------|
| Backend | `backend/hub_client.py` | Obtention du token M2M, appel direct au Hub, helper `send_user_message` | Oui |
| Backend | `backend/main.py` | Expose `/api/config` avec `hub_api_url` et `hub_frontend_url` | Oui |
| Backend | `backend/routes/m2m.py` | Diagnostics admin M2M (`status`, `discover`, `call`) | Optionnel |
| Frontend | `frontend/src/config.js` | Construction des URLs Hub/locales selon HTTP ou HTTPS | Oui |
| Frontend | `frontend/src/context/ConfigContext.jsx` | Charge la config backend et bascule vers `/hub` en HTTPS | Oui |
| Frontend | `frontend/src/context/AuthContext.jsx` | Token utilisateur, refresh, SSE, chargement des messages, accusés de lecture | Oui |
| Frontend | `frontend/src/components/MessageBanner.jsx` | Notifications flottantes actives | Oui |
| Frontend | `frontend/src/components/MessageArchive.jsx` | Historique et badge de messages | Oui |
| Frontend | `frontend/src/styles/index.css` | Styles `message-banner*` et `message-archive*` | Oui |
| Frontend | `frontend/src/App.jsx` | Monte les overlays de messages | Oui |
| Frontend | `frontend/package.json` | Dependance `lucide-react` pour l'UI du bandeau | Oui si reprise telle quelle |
| Infra | `nginx.conf` | Proxy `/hub/` en HTTP | Oui si proxy frontal |
| Infra | `nginx-ssl.conf` | Proxy `/hub/` + reglages SSE en HTTPS | Oui en HTTPS |
| UI admin | `frontend/src/components/M2MTests.jsx` | Ecran de verification admin pour le M2M | Non |

## Cote backend : envoi d'un message via M2M

### Helper deja present dans le template

Le template fournit cette methode dans `backend/hub_client.py` :

```python
async def send_user_message(
    self,
    target_usernames: list[str],
    title: str,
    body: str = None,
    priority: str = "info",
    action_url: str = None,
    action_label: str = None,
    expires_at: str = None,
) -> Optional[dict]:
```

Cette methode construit le payload puis appelle directement le Hub via :

- endpoint Hub : `/api/messages/m2m/send`
- methode HTTP : `POST`
- authentification : token M2M obtenu par `get_m2m_token()`
- header technique ajoute automatiquement : `X-Slug: APP_SLUG`

### Payload envoye au Hub

| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `target_usernames` | `list[str]` | Oui | Usernames Hub des destinataires |
| `title` | `str` | Oui | Titre du message |
| `body` | `str` | Non | Contenu detaille |
| `priority` | `str` | Non | `info`, `warning` ou `urgent` |
| `action_url` | `str` | Non | Lien cliquable dans l'UI |
| `action_label` | `str` | Non | Libelle du bouton d'action |
| `expires_at` | `str` | Non | Date ISO 8601 d'expiration |

Exemple du JSON envoye :

```json
{
  "title": "Validation requise",
  "target_usernames": ["alice", "bob"],
  "priority": "warning",
  "body": "Une action est attendue sur le dossier 1842.",
  "action_url": "https://mon-app.exemple.fr/dossiers/1842",
  "action_label": "Ouvrir le dossier",
  "expires_at": "2026-04-30T18:00:00Z"
}
```

### Exemple d'usage metier

Le bon pattern consiste a appeler `send_user_message` depuis une route metier ou un service applicatif, pas depuis le frontend.

```python
from hub_client import hub_client


async def notifier_validation(target_usernames: list[str], dossier_id: int) -> dict | None:
    return await hub_client.send_user_message(
        target_usernames=target_usernames,
        title="Validation requise",
        body=f"Le dossier {dossier_id} attend votre validation.",
        priority="warning",
        action_url=f"https://mon-app.exemple.fr/dossiers/{dossier_id}",
        action_label="Ouvrir",
    )
```

### Endpoint de demonstration deja disponible dans le template

Pour valider rapidement la chaine complete sans ecrire tout de suite une route metier, le template expose aussi :

```http
POST /api/tests/messages/send
```

Caracteristiques :

- acces reserve aux admins ;
- si `target_usernames` est absent ou vide, le message part vers l'utilisateur courant ;
- l'endpoint appelle directement `hub_client.send_user_message(...)` ;
- si le Hub refuse ou ne confirme pas l'envoi, la route retourne `502`.

Exemple minimal :

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN_ADMIN" \
  http://localhost:9045/api/tests/messages/send
```

Exemple avec payload explicite :

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN_ADMIN" \
  -H "Content-Type: application/json" \
  http://localhost:9045/api/tests/messages/send \
  -d '{
    "target_usernames": ["alice", "bob"],
    "title": "Validation requise",
    "body": "Le dossier 1842 attend votre validation.",
    "priority": "warning",
    "action_url": "https://mon-app.exemple.fr/dossiers/1842",
    "action_label": "Ouvrir"
  }'
```

Cette route doit rester un outil de verification et d'exemple. Pour le metier, il est recommande d'ajouter ensuite une route ou un service dedie, appele par votre logique applicative.

### Ce qu'il faut garder si l'ancienne application a deja le M2M

Si votre ancienne application a deja un client Hub fonctionnel, vous n'avez pas besoin de recopier toute la classe `HubClient`.

Le minimum necessaire est :

1. une methode equivalente a `get_m2m_token()` ;
2. un appel HTTP `POST {hub_api_url}/api/messages/m2m/send` ;
3. le header `Authorization: Bearer <token_m2m>` ;
4. le header `X-Slug: <slug_de_l_app>`.

### Detail important sur les credentials M2M du template

Le template stocke `client_id` et `client_secret` dans `/app/storage/.hub_credentials` pour les partager entre workers. C'est un detail d'implementation du template, pas une obligation fonctionnelle pour la brique messages.

Si l'ancienne application gere deja ses credentials M2M autrement, vous pouvez conserver son mecanisme actuel.

## Cote frontend : lecture, SSE et accusés de lecture

### 1. Configuration recuperee depuis le backend

Le frontend depend de `/api/config`, expose par `backend/main.py`, qui retourne :

```json
{
  "app_slug": "mon-app",
  "app_name": "Mon Application",
  "hub_frontend_url": "http://<hub-host>:80",
  "hub_api_url": "http://<hub-host>:8000",
  "api_url": "http://<app-host>:9045"
}
```

Cette reponse est chargee par `frontend/src/context/ConfigContext.jsx`.

En HTTPS, `ConfigContext` et `frontend/src/config.js` remplacent automatiquement `hub_api_url` par :

```text
https://<origin-app>/hub
```

Ce point est indispensable pour eviter le mixed content et pour faire passer le SSE via le proxy nginx.

### 2. Endpoints Hub utilises par le frontend

Le frontend du template appelle directement les endpoints Hub suivants :

| Endpoint Hub | Methode | Usage |
|--------------|---------|-------|
| `/api/auth/token/refresh` | `POST` | Rafraichir le token utilisateur |
| `/api/events/stream` | `GET` | Flux SSE temps reel |
| `/api/messages/me/unread-count` | `GET` | Badge de messages non lus |
| `/api/messages/me` | `GET` | Liste des messages pour l'archive |
| `/api/messages/{id}/read` | `POST` | Marquer un message comme lu |
| `/api/messages/read-all` | `POST` | Tout marquer comme lu |

Tous les appels HTTP ci-dessus, sauf le SSE, sont faits avec :

```text
Authorization: Bearer <token_utilisateur>
```

### 3. Gestion du flux SSE

Dans `frontend/src/context/AuthContext.jsx`, la connexion est ouverte avec :

```javascript
const sseUrl = `${hubApiUrl}/api/events/stream`
const eventSource = new EventSource(sseUrl)
```

Le code actuel traite les evenements suivants :

| Type d'evenement | Traitement |
|------------------|------------|
| `ping` | Ignore |
| `connected` | Ignore |
| `user_permissions_changed` | Rafraichit le token si l'utilisateur courant est concerne |
| `force_logout` | Deconnecte l'utilisateur |
| `apps_updated` | Rafraichit le token apres approbation ou creation d'app |
| `user_message` | Ajoute le message a l'etat local et l'affiche immediatement |

Sur reception d'un `user_message`, le template fait trois choses :

1. ajoute le message en tete de la liste locale ;
2. incremente le compteur non lu ;
3. ajoute le message a `activeMessages` pour affichage immediat dans `MessageBanner`.

### 4. Structure de message attendue par l'UI

Les composants `MessageBanner` et `MessageArchive` consomment les champs suivants :

| Champ | Usage UI |
|-------|----------|
| `id` | Cle technique pour fermer ou marquer comme lu |
| `title` | Titre principal |
| `body` | Texte detaille |
| `priority` | Style `info`, `warning`, `urgent` |
| `action_url` | Lien cliquable |
| `action_label` | Libelle du lien |
| `sender_app_slug` | Nom technique de l'emetteur |
| `sender_type` | Fallback si `sender_app_slug` absent |
| `created_at` | Horodatage affiche |
| `is_read` | Etat lu / non lu dans l'archive |

Exemple d'objet tel qu'il est exploite par le frontend :

```json
{
  "id": 42,
  "title": "Validation requise",
  "body": "Le dossier 1842 attend votre validation.",
  "priority": "warning",
  "action_url": "https://mon-app.exemple.fr/dossiers/1842",
  "action_label": "Ouvrir",
  "sender_app_slug": "mon-app",
  "sender_type": "app",
  "created_at": "2026-04-11T10:15:00Z",
  "is_read": false
}
```

### 5. Detail important sur l'etat frontend

Dans le template, la variable `unreadMessages` est mal nommee :

- elle sert de source pour l'archive complete ;
- elle est peuplee avec la reponse de `GET /api/messages/me` ;
- elle contient donc potentiellement des messages lus et non lus.

Le vrai indicateur des non lus est `unreadCount`, et l'affichage immediat repose sur `activeMessages`.

### 6. Accusés de lecture

Le template implemente deux actions :

- `markMessageRead(messageId)` appelle `POST /api/messages/{id}/read` ;
- `markAllMessagesRead()` appelle `POST /api/messages/read-all`.

`dismissMessage()` retire le message du bandeau puis appelle `markMessageRead()`.

`dismissAllMessages()` vide le bandeau puis appelle `markAllMessagesRead()`.

## UI embarquee dans le template

### MessageBanner

`frontend/src/components/MessageBanner.jsx` affiche les notifications actives en overlay :

- en haut a droite ;
- avec style different selon la priorite ;
- avec lien d'action optionnel ;
- avec fermeture unitaire ou fermeture globale.

### MessageArchive

`frontend/src/components/MessageArchive.jsx` affiche :

- un bouton flottant en bas a droite ;
- un badge de messages non lus ;
- un panneau lateral d'historique ;
- le statut lu / non lu ;
- l'action "tout marquer comme lu".

### Styles a reprendre

Si vous copiez les composants dans une ancienne application, il faut aussi reprendre les blocs CSS `message-banner*` et `message-archive*` de `frontend/src/styles/index.css`.

Sans ces styles, les composants fonctionneront mais n'auront pas le rendu attendu.

### Dependances frontend a prevoir

Si vous reprenez `MessageBanner.jsx` tel quel, l'application doit avoir :

- `lucide-react`
- `react`
- `react-dom`

## HTTPS et proxy `/hub/`

### Pourquoi le proxy est obligatoire en HTTPS

Quand le frontend tourne en HTTPS, le Hub reste appele en HTTP interne dans ce template. Sans proxy, le navigateur bloquera :

- les appels fetch vers le Hub ;
- le flux SSE ;
- les accusés de lecture.

Le template resout cela avec `location /hub/` dans `nginx.conf` et `nginx-ssl.conf`.

### Contraintes proxy pour le SSE

Le proxy `/hub/` doit au minimum :

- rediriger vers `http://<HUB_HOST>:<HUB_API_PORT>/` ;
- desactiver le buffering ;
- desactiver le cache ;
- autoriser une longue lecture (`proxy_read_timeout` eleve).

Le template le fait deja, y compris dans la configuration SSL.

## Procedure de retrofit pour une ancienne application deja M2M

### Option A : reprise minimale, sans remplacer toute l'auth frontend

Choisir cette option si l'application a deja :

- un contexte d'auth utilisateur ;
- un systeme de refresh token ;
- un client M2M fonctionnel ;
- un layout frontend etabli.

Dans ce cas, reprendre seulement :

1. l'equivalent de `send_user_message()` cote backend ;
2. l'exposition de `hub_api_url` et `hub_frontend_url` dans `/api/config` ;
3. la logique message de `AuthContext` :
   - `unreadMessages`
   - `unreadCount`
   - `activeMessages`
   - chargement initial `/api/messages/me*`
   - marquage lu / tout lu
   - ecoute SSE `user_message`
4. les composants `MessageBanner` et `MessageArchive` ;
5. les styles CSS associes ;
6. le proxy `/hub/` en HTTPS.

### Option B : reprise large des briques du template

Choisir cette option si l'ancienne application n'a pas de logique frontend Hub stabilisee.

Dans ce cas, reprendre presque tels quels :

- `frontend/src/config.js`
- `frontend/src/context/ConfigContext.jsx`
- les parties message de `frontend/src/context/AuthContext.jsx`
- `frontend/src/components/MessageBanner.jsx`
- `frontend/src/components/MessageArchive.jsx`
- les styles correspondants

### Ce qu'il n'est pas necessaire de copier si le M2M existe deja

Si l'ancienne application possede deja un M2M stable, vous pouvez laisser en place :

- l'auto-enregistrement Hub ;
- la decouverte de services ;
- les routes admin `m2m/discover` et `m2m/call` ;
- `M2MTests.jsx` ;
- toute la partie backup/restore.

Pour la brique messages, le noyau utile reste :

- un envoi backend vers `/api/messages/m2m/send` ;
- une lecture frontend via `/api/messages/*` et `/api/events/stream` ;
- l'UI de consultation et de fermeture.

## Check-list de migration

### Backend

- [ ] Le backend connait `APP_SLUG`.
- [ ] Le backend connait `hub_api_url`.
- [ ] Le client Hub peut obtenir un token M2M valide.
- [ ] Un helper envoie `POST /api/messages/m2m/send` avec `Authorization` et `X-Slug`.
- [ ] `/api/config` retourne `hub_api_url` et `hub_frontend_url`.

### Frontend

- [ ] Le frontend connait `hubApiUrl` et `hubFrontendUrl`.
- [ ] Le frontend possede un token utilisateur et un refresh token Hub.
- [ ] Le frontend charge `GET /api/messages/me/unread-count` au login.
- [ ] Le frontend charge `GET /api/messages/me` au login.
- [ ] Le frontend ouvre `EventSource(${hubApiUrl}/api/events/stream)`.
- [ ] Le frontend sait appeler `POST /api/messages/{id}/read`.
- [ ] Le frontend sait appeler `POST /api/messages/read-all`.
- [ ] `MessageBanner` et `MessageArchive` sont montes dans l'application.
- [ ] Les styles des deux composants sont presents.

### Infra

- [ ] En HTTPS, le proxy `/hub/` est configure.
- [ ] Le proxy SSE desactive le buffering.
- [ ] Le timeout de lecture SSE est suffisamment long.

## Verification fonctionnelle recommandee

1. Verifier cote admin que `/api/m2m/status` retourne `registered=true` et `can_get_token=true`.
2. Depuis un flux metier, appeler `send_user_message()` vers un utilisateur de test.
3. Ouvrir une session de cet utilisateur dans le frontend.
4. Verifier que la notification apparait dans `MessageBanner`.
5. Verifier que le badge de `MessageArchive` augmente.
6. Verifier que "Fermer" marque le message comme lu.
7. Verifier que "Tout fermer" ou "tout marquer comme lu" remet le compteur a zero.
8. Verifier qu'en HTTPS il n'y a ni mixed content, ni blocage du SSE.

## Points d'attention

### SSE sans header Authorization explicite

Le code actuel ouvre `EventSource` sans ajouter de header `Authorization`. C'est une limite normale du navigateur avec l'API native EventSource.

Avant retrofit, verifier donc que votre mode d'auth SSE cote Hub est compatible avec ce fonctionnement. Si ce n'est pas le cas, il faudra adapter ce point precis.

### L'UI de messages ne depend pas du backend metier local

Le backend local n'est pas sollicite pour lire ou marquer les messages. Si vous supprimez le proxy `/hub/` ou l'exposition de `hub_api_url`, l'interface de messages cessera de fonctionner meme si le M2M backend reste operationnel.

### Les routes admin M2M ne font pas partie du systeme de messages

`backend/routes/m2m.py` et `frontend/src/components/M2MTests.jsx` sont utiles pour diagnostiquer le M2M, mais ils ne sont pas requis pour la fonctionnalite messages elle-meme.

## Recommandation pratique pour la mise a jour d'une ancienne app

Pour une application existante qui a deja le M2M, la meilleure approche est en general :

1. conserver le client M2M existant ;
2. lui ajouter un helper `send_user_message()` compatible avec le contrat du template ;
3. exposer les URLs Hub via `/api/config` ;
4. greffer la logique frontend messages/SSE ;
5. reprendre l'UI et les styles du template ;
6. valider le comportement en HTTPS avec le proxy `/hub/`.

Cette approche limite le risque de regression, tout en recuperant exactement la logique et l'interface de messages du template.