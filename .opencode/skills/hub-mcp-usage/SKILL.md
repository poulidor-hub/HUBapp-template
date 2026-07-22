---
name: hub-mcp-usage
description: Use when you need to pilot, observe, or administer the Hub via the MCP server — list apps, check Hub health, discover services, manage users, inspect messages, trigger backups, or make raw API calls. The hub MCP exposes ~65 tools (hub_*) that delegate to hub_client. Triggers on: "hubctl", "lister les apps du Hub", "état du Hub", "hub_app", "hub_user", "hub_message", "hub_backup", "MCP hub", "approuver une app", "hub_health".
argument-hint: 'What Hub operation to perform (list apps, check health, send message, discover services, audit logs, etc.)'
---

# Hub MCP Usage

Le serveur MCP `hub` expose **65 outils** (`hub_*`) pour piloter et observer le Hub depuis l'agent opencode. Déclaré dans `opencode.json`, il délègue 100% des appels à un client Hub via `call_hub_endpoint(path, method, json)`.

**Principe :** le MCP est un accès structuré et sécurisé au Hub. Chaque outil mappe vers un endpoint Hub réel. Pas besoin de construire des `curl` ou des `fetch` manuels.

> **Source de vérité :** le catalogue vit dans `hub-mcp/hub_mcp/tools.py` (dépôt dédié). La copie `hub_mcp/` d'une app est un artefact de sync (`make sync-hub-tooling`). Toute modification des outils va dans le dépôt `hub-mcp`, pas dans la copie de l'app.

## ⚠️ Modèle de permissions — mode app (SA) vs standalone (admin)

Le Hub sépare `get_current_user` (rejette les **Service Accounts** → `403 "Endpoint réservé aux utilisateurs"`) de `get_current_entity` (accepte USER **et** SA). Le MCP dispose de **deux modes** (`_LazyHubClient`) :

| Mode | Token utilisé | Endpoints accessibles | Quand l'utiliser |
|------|---------------|----------------------|------------------|
| **App** (dans une app générée) | Service Account (M2M) | Publics + M2M + backups per-app + discovery | Depuis une app (le SA ne peut **pas** se faire passer pour un utilisateur) |
| **Standalone** (méta-repo) | Utilisateur admin (`HUB_ADMIN_USERNAME/PASSWORD`) | **Tous** les endpoints | Piloter le Hub en admin depuis POULIDOR (apps/users/audit/messages admin) |

- En **mode app**, les outils admin/user (`hub_app_list`, `hub_user_*`, `hub_audit_*`, `hub_message_send`, etc.) renvoient `403`. C'est **attendu**, pas un bug.
- Pour débloquer ces outils, passer en **mode standalone** : définir `HUB_BASE_URL`, `HUB_ADMIN_USERNAME`, `HUB_ADMIN_PASSWORD` (ex: dans `.secrets` sourcé par `~/.bashrc`) et lancer le MCP depuis le méta-repo.
- Toujours fonctionnels en mode app : `hub_health`, `hub_system_time`, `hub_config`, `hub_docs_*`, `hub_changelog_*`, `hub_auth_get_jwks`, `hub_discover_services`, `hub_backup_list/get_latest/download`, `hub_message_m2m_send`, `hub_app_register/credentials/regenerate_secret`, `hub_raw_call`.

## Sécurité

Les outils **destructeurs** sont rétrogradés en `ask` par le plugin `.opencode/plugins/hub.ts`. L'agent demandera confirmation avant d'exécuter :
- `hub_app_delete`, `hub_app_approve`, `hub_app_toggle_active`
- `hub_backup_restore`, `hub_backup_delete`
- Toute commande shell destructrice (`rm -rf`, `docker compose down -v`, `DELETE_DATA`, `drop database`, `git push --force`, `clean-all`)

Voir `.opencode/plugins/hub.ts` pour la liste exhaustive et le mécanisme.

## Catalogue des outils par domaine

> Légende : 🔓 = public/SA-accessible en mode app · 🔒 = réservé aux utilisateurs (403 en mode app → mode standalone requis).

### Apps

| Outil | Rôle | |
|-------|------|--|
| `hub_app_list` | Lister toutes les apps enregistrées (statut, ports, slug, nom) | 🔒 |
| `hub_app_get` | Détail d'une app spécifique | 🔒 |
| `hub_app_create` | Créer une app dans le registre Hub | 🔒 |
| `hub_app_update` | Modifier les infos d'une app | 🔒 |
| `hub_app_register` | Enregistrer l'app courante (auto-enregistrement) | 🔓 |
| `hub_app_get_credentials` | Obtenir `client_id` + statut secret/token M2M | 🔓 |
| `hub_app_regenerate_secret` | Régénérer le secret M2M (révoque l'ancien) | 🔓 |
| `hub_app_set_users` | Assigner des utilisateurs aux rôles d'une app | 🔒 |
| `hub_app_toggle_shared` | Activer/désactiver `IS_SHARED` | 🔒 |
| `hub_app_approve` | Approuver une app en attente (admin only) ⚠️ | 🔒 |
| `hub_app_toggle_active` | Activer/désactiver une app ⚠️ | 🔒 |
| `hub_app_delete` | Supprimer définitivement une app du registre ⚠️ | 🔒 |
| `hub_app_docker_scan` | Scanner les conteneurs Docker actifs | 🔒 |

### Users

| Outil | Rôle | |
|-------|------|--|
| `hub_user_list` | Lister tous les utilisateurs Hub | 🔒 |
| `hub_user_get` | Détail d'un utilisateur | 🔒 |
| `hub_user_create` | Créer un nouvel utilisateur | 🔒 |
| `hub_user_update` | Modifier un utilisateur | 🔒 |
| `hub_user_set_app_roles` | Assigner des rôles (par app) à un utilisateur | 🔒 |
| `hub_user_bulk_create` | Créer plusieurs utilisateurs en une fois | 🔒 |
| `hub_user_bulk_roles` | Assigner des rôles à plusieurs utilisateurs à la fois | 🔒 |

### Messages (notifications)

| Outil | Rôle | |
|-------|------|--|
| `hub_message_m2m_send` | Envoyer un message via M2M (SA) | 🔓 |
| `hub_message_send` | Envoyer un message (admin) | 🔒 |
| `hub_message_list` | Lister les messages (admin, paginé, filtrable) | 🔒 |
| `hub_message_my_list` | Mes messages (utilisateur courant) | 🔒 |
| `hub_message_my_unread_count` | Compteur de messages non-lus | 🔒 |
| `hub_message_read` | Marquer un message comme lu | 🔒 |
| `hub_message_stats` | Statistiques agrégées des messages | 🔒 |

### Discovery & M2M

| Outil | Rôle | |
|-------|------|--|
| `hub_discover_services` | Lister les services partagés (IS_SHARED=true) | 🔓 |
| `hub_call_service` | Appeler un service distant via M2M | 🔓 |

### Backups

| Outil | Rôle | |
|-------|------|--|
| `hub_backup_list` | Lister les backups d'une app (`app_slug`) | 🔓 |
| `hub_backup_get_latest` | Dernier backup d'une app (`app_slug`) | 🔓 |
| `hub_backup_download` | Télécharger un backup (`app_slug`, `backup_id`) | 🔓 |
| `hub_backup_config_get` | Configuration de backup d'une app | 🔒 |
| `hub_backup_config_update` | Modifier la config de backup | 🔒 |
| `hub_backup_delete` | Supprimer un backup ⚠️ | 🔒 |
| `hub_backup_restore` | Restaurer un backup ⚠️ | 🔒 |
| `hub_backup_stats` | Statistiques des backups (taille, nombre) | 🔒 |
| `hub_backup_orphans_list` | Lister les backups orphelins | 🔒 |
| `hub_backup_trigger` | Déclencher un backup manuel (`app_slug`) | 🔒 |

### Audit

| Outil | Rôle | |
|-------|------|--|
| `hub_audit_logs` | Logs d'audit (connexions, actions) | 🔒 |
| `hub_audit_sessions` | Sessions actives | 🔒 |
| `hub_audit_sessions_history` | Historique des sessions | 🔒 |
| `hub_audit_stats` | Statistiques d'audit | 🔒 |
| `hub_audit_errors` | Erreurs système | 🔒 |
| `hub_audit_errors_stats` | Statistiques d'erreurs | 🔒 |
| `hub_audit_error_detail` | Détail d'une erreur | 🔒 |
| `hub_audit_errors_acknowledge` | Acquitter des erreurs | 🔒 |

### Auth

| Outil | Rôle | |
|-------|------|--|
| `hub_auth_login` | Login utilisateur (password grant → JWT) | 🔓 |
| `hub_auth_me` | Infos du token courant (utilisateur) | 🔒 |
| `hub_auth_get_m2m_token` | Obtenir un token M2M (client_credentials) | 🔓 |
| `hub_auth_get_jwks` | Récupérer les clés JWKS | 🔓 |
| `hub_auth_token_introspect` | Introspecter un token (admin ou SA) | 🔒 |
| `hub_auth_create_bootstrap_token` | Créer un token bootstrap (admin initial) | 🔒 |
| `hub_auth_list_bootstrap_tokens` | Lister les tokens bootstrap | 🔒 |

### Documentation

| Outil | Rôle | |
|-------|------|--|
| `hub_docs_get` | Récupérer la documentation intégrée | 🔓 |
| `hub_docs_sections` | Lister les sections de documentation | 🔓 |
| `hub_changelog_get` | Récupérer le CHANGELOG du Hub | 🔓 |
| `hub_changelog_diff` | Diff entre deux versions du CHANGELOG | 🔓 |

### Admin / Système

| Outil | Rôle | |
|-------|------|--|
| `hub_health` | Healthcheck du Hub | 🔓 |
| `hub_config` | Hôte public du Hub (`/api/config/hub-host`) | 🔓 |
| `hub_system_time` | Heure système du Hub | 🔓 |
| `hub_admin_settings` | Lire un paramètre par sa clé (`key`) | 🔒 |
| `hub_admin_ports_status` | État de l'allocation des ports | 🔒 |
| `hub_raw_call` | Appel HTTP brut à un endpoint Hub (méthode, body, params libres) | 🔓 |

> **Outils retirés (v0.3.0)** — routes inexistantes sur le Hub v3.12 : `hub_pki_*`, `hub_design_*`, `hub_admin_info`, `hub_admin_dns_status`, `hub_discovery_proxy`, `hub_backup_export_env`, `hub_backup_import_env`, `hub_user_reset_password`.

## Cas d'usage typiques

### Observer l'état du parc

```
Agent → hub_health         # Le Hub répond-il ?
Agent → hub_app_list       # Quelles apps sont enregistrées ? (mode standalone)
Agent → hub_user_list      # Quels utilisateurs existent ? (mode standalone)
Agent → hub_audit_stats    # Activité récente ? (mode standalone)
```

### Vérifier une app après création

```
Agent → hub_app_list                  # L'app apparaît dans la liste ? (standalone)
Agent → hub_app_get app_id=...        # Détail : ports, statut, approbation
Agent → hub_app_approve app_slug=...  # Approuver si en attente
Agent → hub_discover_services         # Si IS_SHARED, elle apparaît ici ? (SA ok)
```

### Diagnostiquer un problème M2M

```
Agent → hub_discover_services            # Le service cible est-il visible ? (SA ok)
Agent → hub_call_service slug=cible ...   # Appeler manuellement pour tester
Agent → hub_audit_errors                  # Erreurs récentes côté Hub ? (standalone)
Agent → hub_message_m2m_send ...          # Envoyer un message de test (SA ok)
```

### Backup

```
Agent → hub_backup_list app_slug=mon-app   # Quels backups existent ? (SA ok)
Agent → hub_backup_stats                   # Taille, âge ? (standalone)
Agent → hub_backup_trigger app_slug=mon-app # Déclencher un backup (standalone)
```

## Quand utiliser le MCP vs le code direct

| Situation | Utiliser | Raison |
|-----------|----------|--------|
| Observer l'état (lister, vérifier, diagnostiquer) | MCP `hub_*` | Plus rapide, pas besoin d'écrire du code |
| Appeler un service dans une route backend | `hub_client.call_discovered_service()` | Code applicatif, doit être dans le fichier |
| Envoyer une notification | `hub_client.send_user_message()` | Code applicatif |
| Faire un appel brut non couvert | `hub_raw_call` | Flexibilité max |
| Tâche admin ponctuelle | MCP `hub_*` (mode standalone) | Pas besoin de persister du code |

## Références

| Réf | Chemin |
|-----|--------|
| Serveur MCP (source canonique) | `hub-mcp/hub_mcp/tools.py` (dépôt dédié, 65 outils) |
| Client standalone (admin) | `hub-mcp/hub_mcp/standalone_client.py` (mode `HUB_ADMIN_*`) |
| Plugin sécurité | `.opencode/plugins/hub.ts` (rétrogradation des ops destructrices) |
| hub_client (mode app) | `backend/hub_client.py` (utilisé par le MCP dans une app) |
| opencode.json template | `opencode.json` (déclaration du MCP `hub`) |
