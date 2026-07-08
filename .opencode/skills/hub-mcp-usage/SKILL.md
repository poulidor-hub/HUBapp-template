---
name: hub-mcp-usage
description: Use when you need to pilot, observe, or administer the Hub via the MCP server — list apps, check Hub health, discover services, manage users, inspect messages, trigger backups, or make raw API calls. The hub MCP exposes ~85 tools (hub_*) that delegate to hub_client. Triggers on: "hubctl", "lister les apps du Hub", "état du Hub", "hub_app", "hub_user", "hub_message", "hub_backup", "MCP hub", "approuver une app", "hub_health".
argument-hint: 'What Hub operation to perform (list apps, check health, send message, discover services, audit logs, etc.)'
---

# Hub MCP Usage

Le serveur MCP `hub` expose ~85 outils (`hub_*`) pour piloter et observer le Hub depuis l'agent opencode. Déclaré dans `opencode.json` du template, il délègue 100% des appels à `backend.hub_client.hub_client` de l'app hôte.

**Principe :** le MCP est un accès structuré et sécurisé au Hub. Chaque outil mappe vers un endpoint Hub réel, avec l'auth M2M gérée automatiquement. Pas besoin de construire des `curl` ou des `fetch` manuels.

## Sécurité

Les outils **destructeurs** sont rétrogradés en `ask` par le plugin `.opencode/plugins/hub.ts`. Cela signifie que l'agent demandera confirmation avant d'exécuter :
- `hub_app_delete`, `hub_app_approve`, `hub_app_toggle_active`
- `hub_backup_restore`, `hub_backup_delete`
- `hub_pki_revoke_cert`, `hub_user_reset_password`
- `hub_message_delete`, `hub_message_batch_delete`
- Toute commande shell destructrice (`rm -rf`, `docker compose down -v`, `DELETE_DATA`, `drop database`, `git push --force`, `clean-all`)

Voir `.opencode/plugins/hub.ts` pour la liste exhaustive et le mécanisme.

## Catalogue des outils par domaine

### Apps

| Outil | Rôle |
|-------|------|
| `hub_app_list` | Lister toutes les apps enregistrées (statut, ports, slug, nom) |
| `hub_app_get` | Détail d'une app spécifique |
| `hub_app_create` | Créer une app dans le registre Hub |
| `hub_app_update` | Modifier les infos d'une app |
| `hub_app_register` | Enregistrer une app (auto-enregistrement externe) |
| `hub_app_get_credentials` | Obtenir `client_id` + `client_secret` M2M d'une app |
| `hub_app_regenerate_secret` | Régénérer le secret M2M (révoque l'ancien) |
| `hub_app_set_users` | Assigner des utilisateurs aux rôles d'une app |
| `hub_app_toggle_shared` | Activer/désactiver `IS_SHARED` |
| `hub_app_approve` | Approuver une app en attente (admin only) ⚠️ |
| `hub_app_toggle_active` | Activer/désactiver une app ⚠️ |
| `hub_app_delete` | Supprimer définitivement une app du registre ⚠️ |
| `hub_app_docker_scan` | Scanner les conteneurs Docker actifs et synchroniser le registre |

### Users

| Outil | Rôle |
|-------|------|
| `hub_user_list` | Lister tous les utilisateurs Hub |
| `hub_user_get` | Détail d'un utilisateur |
| `hub_user_create` | Créer un nouvel utilisateur |
| `hub_user_update` | Modifier un utilisateur |
| `hub_user_reset_password` | Réinitialiser le mot de passe ⚠️ |
| `hub_user_set_app_roles` | Assigner des rôles (par app) à un utilisateur |
| `hub_user_bulk_create` | Créer plusieurs utilisateurs en une fois |
| `hub_user_bulk_roles` | Assigner des rôles à plusieurs utilisateurs à la fois |

### Messages (notifications)

| Outil | Rôle |
|-------|------|
| `hub_message_send` | Envoyer un message (admin) |
| `hub_message_m2m_send` | Envoyer un message via M2M (SA) |
| `hub_message_list` | Lister les messages (admin, paginé, filtrable) |
| `hub_message_my_list` | Mes messages (utilisateur courant) |
| `hub_message_my_unread_count` | Compteur de messages non-lus |
| `hub_message_read` | Marquer un message comme lu |
| `hub_message_stats` | Statistiques agrégées des messages |

### Discovery & M2M

| Outil | Rôle |
|-------|------|
| `hub_discover_services` | Lister les services partagés (IS_SHARED=true) |
| `hub_call_service` | Appeler un service distant via M2M |
| `hub_discovery_proxy` | Proxy discovery brut |

### Backups

| Outil | Rôle |
|-------|------|
| `hub_backup_export_env` | Exporter les .env chiffrés du parc |
| `hub_backup_import_env` | Importer des .env (restauration) |
| `hub_backup_list` | Lister les backups disponibles |
| `hub_backup_get` | Détail d'un backup |
| `hub_backup_latest` | Dernier backup |
| `hub_backup_download` | Télécharger un backup |
| `hub_backup_config_get` | Configuration actuelle des backups |
| `hub_backup_config_update` | Modifier la config de backup |
| `hub_backup_delete` | Supprimer un backup ⚠️ |
| `hub_backup_restore` | Restaurer un backup ⚠️ |
| `hub_backup_stats` | Statistiques des backups (taille, nombre) |
| `hub_backup_orphans_list` | Lister les backups orphelins |
| `hub_backup_trigger` | Déclencher un backup manuel |

### Audit

| Outil | Rôle |
|-------|------|
| `hub_audit_logs` | Logs d'audit (connexions, actions) |
| `hub_audit_sessions` | Sessions actives |
| `hub_audit_sessions_history` | Historique des sessions |
| `hub_audit_stats` | Statistiques d'audit |
| `hub_audit_errors` | Erreurs système |
| `hub_audit_errors_stats` | Statistiques d'erreurs |
| `hub_audit_error_detail` | Détail d'une erreur |
| `hub_audit_errors_acknowledge` | Acquitter des erreurs |

### Auth

| Outil | Rôle |
|-------|------|
| `hub_auth_login` | Login utilisateur (retourne JWT) |
| `hub_auth_me` | Infos du token courant |
| `hub_auth_get_m2m_token` | Obtenir un token M2M (client_credentials) |
| `hub_auth_get_jwks` | Récupérer les clés JWKS |
| `hub_auth_token_introspect` | Introspecter un token |
| `hub_auth_create_bootstrap_token` | Créer un token bootstrap (admin initial) |
| `hub_auth_list_bootstrap_tokens` | Lister les tokens bootstrap |

### Design System

| Outil | Rôle |
|-------|------|
| `hub_design_manifest` | Récupérer le manifest du design system |
| `hub_design_status` | Statut du design system |
| `hub_design_upload` | Uploader une nouvelle version HUBCSS |

### Documentation

| Outil | Rôle |
|-------|------|
| `hub_docs_get` | Récupérer la documentation intégrée |
| `hub_docs_sections` | Lister les sections de documentation |
| `hub_changelog_get` | Récupérer le CHANGELOG du Hub |
| `hub_changelog_diff` | Diff entre deux versions du CHANGELOG |

### PKI / Certificats

| Outil | Rôle |
|-------|------|
| `hub_pki_ca_info` | Infos sur l'autorité de certification |
| `hub_pki_list_certs` | Certificats émis |
| `hub_pki_revoke_cert` | Révoquer un certificat ⚠️ |

### Admin / Système

| Outil | Rôle |
|-------|------|
| `hub_admin_info` | Informations d'administration (version, uptime) |
| `hub_admin_settings` | Paramètres du Hub |
| `hub_admin_ports_status` | État de l'allocation des ports |
| `hub_admin_dns_status` | État DNS |
| `hub_health` | Healthcheck du Hub |
| `hub_config` | Configuration du Hub |
| `hub_system_time` | Heure système du Hub |
| `hub_raw_call` | Appel HTTP brut à un endpoint Hub (méthode, body, params libres) |

## Cas d'usage typiques

### Observer l'état du parc

```
Agent → hub_health         # Le Hub répond-il ?
Agent → hub_app_list       # Quelles apps sont enregistrées ? Leur statut ?
Agent → hub_user_list      # Quels utilisateurs existent ?
Agent → hub_audit_stats    # Activité récente ?
```

### Vérifier une app après création

```
Agent → hub_app_list       # L'app apparaît dans la liste ?
Agent → hub_app_get slug=mon-app  # Détail : ports, statut, approbation
Agent → hub_app_approve slug=mon-app  # Approuver si en attente
Agent → hub_discover_services  # Si IS_SHARED, elle apparaît ici ?
```

### Diagnostiquer un problème M2M

```
Agent → hub_discover_services            # Le service cible est-il visible ?
Agent → hub_call_service slug=cible ...   # Appeler manuellement pour tester
Agent → hub_audit_errors                  # Erreurs récentes côté Hub ?
Agent → hub_message_m2m_send ...          # Envoyer un message de test
```

### Gérer les utilisateurs

```
Agent → hub_user_list                    # Qui existe ?
Agent → hub_user_create username=...     # Créer un nouvel utilisateur
Agent → hub_user_set_app_roles           # Assigner des rôles dans une app
```

### Backup

```
Agent → hub_backup_list                  # Quels backups existent ?
Agent → hub_backup_stats                 # Taille, âge ?
Agent → hub_backup_trigger               # Déclencher un backup manuel
```

## Quand utiliser le MCP vs le code direct

| Situation | Utiliser | Raison |
|-----------|----------|--------|
| Observer l'état (lister, vérifier, diagnostiquer) | MCP `hub_*` | Plus rapide, pas besoin d'écrire du code |
| Appeler un service dans une route backend | `hub_client.call_discovered_service()` | Code applicatif, doit être dans le fichier |
| Envoyer une notification | `hub_client.send_user_message()` | Code applicatif |
| Faire un appel brut non couvert | `hub_raw_call` | Flexibilité max |
| Tâche admin ponctuelle | MCP `hub_*` | Pas besoin de persister du code |

## Références

| Réf | Chemin |
|-----|--------|
| Serveur MCP | `hub-mcp/hub_mcp/tools.py` (surface complète) |
| Plugin sécurité | `.opencode/plugins/hub.ts` (rétrogradation des ops destructrices) |
| hub_client | `backend/hub_client.py` (1043 lignes, utilisé par le MCP) |
| opencode.json template | `opencode.json` (déclaration du MCP `hub`) |
