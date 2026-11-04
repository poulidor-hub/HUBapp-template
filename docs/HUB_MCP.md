# Catalogue des outils MCP du Hub (copie embarquée : 63 outils)

> Source de vérité : dépôt `hub-mcp` (plugin `hub.ts` / `hub_mcp/tools.py`). Ce document est un miroir de référence pour navigation rapide ; en cas de doute, la liste réelle est celle exposée par le serveur MCP actif. La copie `hub_mcp/` d'une app est un artefact de sync (`make sync-hub-tooling`) — toute modification des outils va dans le dépôt `hub-mcp`, pas dans la copie de l'app.

Le serveur MCP `hub` embarqué avec ce template expose **63 outils** (`hub_*`) pour piloter et observer le Hub depuis l'agent opencode. Déclaré dans `opencode.json`, il délègue 100% des appels à un client Hub via `call_hub_endpoint(path, method, json)`. Chaque outil mappe vers un endpoint Hub réel — pas besoin de construire des `curl` ou `fetch` manuels.

> Légende : 🔓 = public/SA-accessible en mode app · 🔒 = réservé aux utilisateurs (403 en mode app → mode standalone requis). ⚠️ = opération destructive (rétrogradée en `ask` par le plugin de sécurité, voir le skill `hub-mcp-usage`).

## Apps

| Outil | Rôle | |
|-------|------|--|
| `hub_app_list` | Lister toutes les apps enregistrées (statut, ports, slug, nom) | 🔒 |
| `hub_app_get` | Détail d'une app spécifique | 🔒 |
| `hub_app_create` | Créer une app dans le registre Hub | 🔒 |
| `hub_app_update` | Modifier les infos d'une app | 🔒 |
| `hub_app_register` | Enregistrer l'app courante (auto-enregistrement) | 🔓 |
| `hub_app_get_credentials` | Obtenir `client_id` + statut secret/token M2M | 🔓 |
| `hub_app_regenerate_secret` | Régénérer le secret M2M (révoque l'ancien) ⚠️ | 🔓 |
| `hub_app_set_users` | Assigner des utilisateurs aux rôles d'une app | 🔒 |
| `hub_app_toggle_shared` | Activer/désactiver `IS_SHARED` | 🔒 |
| `hub_app_approve` | Approuver une app en attente (admin only) ⚠️ | 🔒 |
| `hub_app_toggle_active` | Activer/désactiver une app ⚠️ | 🔒 |
| `hub_app_delete` | Supprimer définitivement une app du registre ⚠️ | 🔒 |
| `hub_app_docker_scan` | Scanner les conteneurs Docker actifs | 🔒 |

## Users

| Outil | Rôle | |
|-------|------|--|
| `hub_user_list` | Lister tous les utilisateurs Hub | 🔒 |
| `hub_user_get` | Détail d'un utilisateur | 🔒 |
| `hub_user_create` | Créer un nouvel utilisateur | 🔒 |
| `hub_user_update` | Modifier un utilisateur | 🔒 |
| `hub_user_set_app_roles` | Assigner des rôles (par app) à un utilisateur | 🔒 |
| `hub_user_bulk_create` | Créer plusieurs utilisateurs en une fois | 🔒 |
| `hub_user_bulk_roles` | Assigner des rôles à plusieurs utilisateurs à la fois | 🔒 |

## Messages (notifications)

| Outil | Rôle | |
|-------|------|--|
| `hub_message_m2m_send` | Envoyer un message via M2M (SA) | 🔓 |
| `hub_message_send` | Envoyer un message (admin) | 🔒 |
| `hub_message_list` | Lister les messages (admin, paginé, filtrable) | 🔒 |
| `hub_message_my_list` | Mes messages (utilisateur courant) | 🔒 |
| `hub_message_my_unread_count` | Compteur de messages non-lus | 🔒 |
| `hub_message_read` | Marquer un message comme lu | 🔒 |
| `hub_message_stats` | Statistiques agrégées des messages | 🔒 |

## Discovery & M2M

| Outil | Rôle | |
|-------|------|--|
| `hub_discover_services` | Lister les services partagés (IS_SHARED=true) | 🔓 |
| `hub_call_service` | Appeler un service distant via M2M | 🔓 |

## Backups

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

## Audit

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

## Auth

| Outil | Rôle | |
|-------|------|--|
| `hub_auth_login` | Login utilisateur (password grant → JWT) | 🔓 |
| `hub_auth_me` | Infos du token courant (utilisateur) | 🔒 |
| `hub_auth_get_m2m_token` | Obtenir un token M2M (client_credentials) | 🔓 |
| `hub_auth_get_jwks` | Récupérer les clés JWKS | 🔓 |
| `hub_auth_token_introspect` | Introspecter un token (admin ou SA) | 🔒 |

## Documentation

| Outil | Rôle | |
|-------|------|--|
| `hub_docs_get` | Récupérer la documentation intégrée | 🔓 |
| `hub_docs_sections` | Lister les sections de documentation | 🔓 |
| `hub_changelog_get` | Récupérer le CHANGELOG du Hub | 🔓 |
| `hub_changelog_diff` | Diff entre deux versions du CHANGELOG | 🔓 |

## Admin / Système

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

> ℹ️ Copie vendue avec le template (63 outils). Le serveur [`hub-mcp`](https://github.com/POULIDOR-Audit-Developpement/hub-mcp) v0.16.x expose **66 outils** — pensez à resynchroniser la copie embarquée (`make sync-hub-tooling`) pour bénéficier du catalogue complet.
