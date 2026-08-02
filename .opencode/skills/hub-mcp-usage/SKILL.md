---
name: hub-mcp-usage
description: Use when you need to pilot, observe, or administer the Hub via the MCP server — list apps, check Hub health, discover services, manage users, inspect messages, trigger backups, or make raw API calls. Le savoir-faire (modèle de permissions SA/standalone, MCP vs code direct, sécurité) vit ici ; le catalogue exhaustif des ~65 outils `hub_*` vit dans `docs/HUB_MCP.md`. Triggers on: "hubctl", "lister les apps du Hub", "état du Hub", "hub_app", "hub_user", "hub_message", "hub_backup", "MCP hub", "approuver une app", "hub_health".
argument-hint: 'What Hub operation to perform (list apps, check health, send message, discover services, audit logs, etc.)'
---

# Hub MCP Usage

Le serveur MCP `hub` expose **~65 outils** (`hub_*`) qui délèguent 100% des appels au Hub via `call_hub_endpoint(path, method, json)`. Chaque outil mappe vers un endpoint réel — pas de `curl`/`fetch` manuels. Pour la liste exhaustive des outils et signatures, voir **Catalogue complet** ci-dessous.

## ⚠️ Modèle de permissions — mode app (SA) vs standalone (admin)

Le Hub sépare `get_current_user` (rejette les **Service Accounts** → `403 "Endpoint réservé aux utilisateurs"`) de `get_current_entity` (accepte USER **et** SA). Le MCP dispose de **deux modes** (`_LazyHubClient`) :

| Mode | Token utilisé | Endpoints accessibles | Quand l'utiliser |
|------|---------------|----------------------|------------------|
| **App** (dans une app générée) | Service Account (M2M) | Publics + M2M + backups per-app + discovery | Depuis une app (le SA ne peut **pas** se faire passer pour un utilisateur) |
| **Standalone** (méta-repo) | Utilisateur admin (`HUB_ADMIN_USERNAME/PASSWORD`) | **Tous** les endpoints | Piloter le Hub en admin depuis POULIDOR (apps/users/audit/messages admin) |

- En **mode app**, les outils admin/user (`hub_app_list`, `hub_user_*`, `hub_audit_*`, `hub_message_send`, etc.) renvoient `403`. C'est **attendu**, pas un bug.
- Pour débloquer ces outils, passer en **mode standalone** : définir `HUB_BASE_URL`, `HUB_ADMIN_USERNAME`, `HUB_ADMIN_PASSWORD` (ex: dans `.secrets` sourcé par `~/.bashrc`) et lancer le MCP depuis le méta-repo.
- Toujours fonctionnels en mode app : `hub_health`, `hub_system_time`, `hub_config`, `hub_docs_*`, `hub_changelog_*`, `hub_auth_get_jwks`, `hub_discover_services`, `hub_backup_list/get_latest/download`, `hub_message_m2m_send`, `hub_app_register/credentials/regenerate_secret`, `hub_raw_call`.

## Sécurité — rétrogradation `ask`

Les outils **destructeurs** sont rétrogradés en mode `ask` par le plugin `.opencode/plugins/hub.ts` : l'agent **doit obtenir une confirmation explicite** avant exécution. Concerne notamment :
- `hub_app_delete`, `hub_app_approve`, `hub_app_toggle_active`
- `hub_backup_restore`, `hub_backup_delete`, `hub_app_regenerate_secret` (révoque l'ancien secret)

Toute commande shell destructrice (`rm -rf`, `docker compose down -v`, `DELETE_DATA`, `drop database`, `git push --force`, `clean-all`) est également rétrogradée. Liste exhaustive et mécanisme dans `.opencode/plugins/hub.ts`.

## MCP vs code direct

| Situation | Utiliser | Raison |
|-----------|----------|--------|
| Observer l'état (lister, vérifier, diagnostiquer) | MCP `hub_*` | Plus rapide, pas besoin d'écrire du code |
| Appeler un service dans une route backend | `hub_client.call_discovered_service()` | Code applicatif, doit vivre dans le fichier |
| Envoyer une notification | `hub_client.send_user_message()` | Code applicatif |
| Faire un appel brut non couvert | `hub_raw_call` | Flexibilité max |
| Tâche admin ponctuelle | MCP `hub_*` (mode standalone) | Pas besoin de persister du code |

## Catalogue complet

Le catalogue exhaustif (outils par domaine, signatures, badges 🔓/🔒 de permissions, outils retirés, cas d'usage typiques) vit dans [docs/HUB_MCP.md](../../../docs/HUB_MCP.md). C'est un miroir du dépôt `hub-mcp` ; en cas de doute, la liste réelle est celle exposée par le serveur MCP actif.

## Références

| Réf | Chemin |
|-----|--------|
| Catalogue des outils | [docs/HUB_MCP.md](../../../docs/HUB_MCP.md) |
| Serveur MCP (source canonique) | `hub-mcp/hub_mcp/tools.py` (dépôt dédié, ~65 outils) |
| Sync vers une app | `make sync-hub-tooling` (re-genère la copie `hub_mcp/` de l'app) |
| Client standalone (admin) | `hub-mcp/hub_mcp/standalone_client.py` (mode `HUB_ADMIN_*`) |
| Plugin sécurité | `.opencode/plugins/hub.ts` (rétrogradation des ops destructrices) |
| hub_client (mode app) | `backend/hub_client.py` (utilisé par le MCP dans une app) |
| Déclaration MCP | `opencode.json` (entrée du serveur `hub`) |
