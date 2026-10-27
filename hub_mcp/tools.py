"""
Registre des tools MCP exposes par le serveur Hub Tools.
Chaque tool utilise hub_client.call_hub_endpoint() pour communiquer avec le HUB.
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from mcp.types import Tool, TextContent


class _LazyHubClient:
    """Proxy a resolution paresseuse vers un client Hub.

    Deux modes, résolus au premier appel d'outil :

    1. **Mode app** : ``backend.hub_client`` (depuis une app générée par
       ``HUBapp_TEMPLATE_base``, qui expose le paquet ``backend``).
    2. **Mode standalone** : ``hub_mcp.standalone_client.StandaloneHubClient``
       (client HTTP direct via httpx). Utilisé hors app — typiquement depuis le
       méta-repo POULIDOR — configuré par ``HUB_BASE_URL`` /
       ``HUB_ADMIN_USERNAME`` / ``HUB_ADMIN_PASSWORD``.

    Le serveur MCP démarre (et liste ses tools) même si aucun backend n'est
    joignable ; seuls les appels d'outils échouent alors, avec un message clair.
    """

    _client = None

    @classmethod
    def _resolve(cls):
        if cls._client is None:
            # 1. Mode app : backend.hub_client (depuis une app HUBapp_TEMPLATE_base)
            try:
                from backend.hub_client import hub_client as real
                cls._client = real
            except Exception:
                # 2. Mode standalone : client HTTP direct (depuis le méta-repo, via env)
                try:
                    from hub_mcp.standalone_client import StandaloneHubClient
                    cls._client = StandaloneHubClient()
                except Exception as exc2:
                    raise RuntimeError(
                        "hub_mcp: aucun backend utilisable. Soit lancer depuis une app "
                        "HUBapp_TEMPLATE_base (expose `backend.hub_client`), soit définir "
                        "les variables d'env HUB_BASE_URL / HUB_ADMIN_USERNAME / "
                        "HUB_ADMIN_PASSWORD pour le mode standalone (ex: méta-repo, dans .secrets)."
                    ) from exc2
        return cls._client

    def __getattr__(self, name):
        return getattr(_LazyHubClient._resolve(), name)

    def __setattr__(self, name, value):
        setattr(_LazyHubClient._resolve(), name, value)

    def __delattr__(self, name):
        delattr(_LazyHubClient._resolve(), name)


hub_client = _LazyHubClient()

# ============================================================
# TOOL DEFINITIONS
# ============================================================

TOOLS = [
    # --- Health ---
    Tool(
        name="hub_health",
        description="Verifie l'etat de sante du HUB (health check).",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="hub_config",
        description="Recupere l'hote public du HUB (GET /api/config/hub-host).",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="hub_system_time",
        description="Recupere l'heure systeme UTC du serveur HUB.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    # --- Raw call ---
    Tool(
        name="hub_raw_call",
        description="Appelle un endpoint arbitraire de l'API Hub avec authentification M2M.",
        inputSchema={
            "type": "object",
            "properties": {
                "endpoint": {"type": "string", "description": "Endpoint Hub (ex: /api/health)"},
                "path": {"type": "string", "description": "Alias pour endpoint"},
                "method": {"type": "string", "description": "Methode HTTP (GET, POST, PUT, DELETE)", "default": "GET"},
                "body": {"type": "object", "description": "Corps JSON (POST/PUT)"},
            },
            "required": [],
        },
    ),
    # --- App Management ---
    Tool(
        name="hub_app_list",
        description="Liste toutes les applications enregistrees sur le HUB (filtre par role si non-admin).",
        inputSchema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Numero de page (default 1)"},
                "per_page": {"type": "integer", "description": "Elements par page (default 20)"},
                "search": {"type": "string", "description": "Recherche par nom ou slug"},
            },
            "required": [],
        },
    ),
    Tool(
        name="hub_app_get",
        description="Recupere les details d'une application par son ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "app_id": {"type": "integer", "description": "ID de l'application"},
            },
            "required": ["app_id"],
        },
    ),
    Tool(
        name="hub_app_create",
        description="Cree une nouvelle application sur le HUB (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Slug unique"},
                "name": {"type": "string", "description": "Nom affiche"},
                "description": {"type": "string", "description": "Description (optionnel)"},
                "is_shared_service": {"type": "boolean", "description": "Service partage M2M"},
            },
            "required": ["slug", "name"],
        },
    ),
    Tool(
        name="hub_app_update",
        description="Met a jour une application sur le HUB (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "app_id": {"type": "integer", "description": "ID de l'app a modifier"},
                "name": {"type": "string", "description": "Nouveau nom"},
                "description": {"type": "string", "description": "Nouvelle description"},
            },
            "required": ["app_id"],
        },
    ),
    Tool(
        name="hub_app_delete",
        description="Supprime une application du HUB (admin requis, cascade SA + credentials).",
        inputSchema={
            "type": "object",
            "properties": {
                "app_id": {"type": "integer", "description": "ID de l'app a supprimer"},
            },
            "required": ["app_id"],
        },
    ),
    Tool(
        name="hub_app_toggle_active",
        description="Active ou desactive une application (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "app_id": {"type": "integer", "description": "ID de l'application"},
            },
            "required": ["app_id"],
        },
    ),
    Tool(
        name="hub_app_register",
        description="Auto-enregistre l'application courante (celle du template) aupres du HUB.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="hub_app_get_credentials",
        description="Lit les credentials M2M locales de l'application courante.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="hub_app_regenerate_secret",
        description="Regenere le client secret de l'application aupres du HUB.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="hub_app_set_users",
        description="Assigne des utilisateurs a une application avec leurs roles (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "app_id": {"type": "integer", "description": "ID de l'application"},
                "user_ids": {"type": "array", "items": {"type": "integer"}, "description": "Liste des IDs utilisateurs"},
            },
            "required": ["app_id", "user_ids"],
        },
    ),
    Tool(
        name="hub_app_toggle_shared",
        description="Active/desactive le flag IS_SHARED d'une application (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "app_id": {"type": "integer"},
                "shared": {"type": "boolean"},
            },
            "required": ["app_id", "shared"],
        },
    ),
    Tool(
        name="hub_app_approve",
        description="Approuve ou rejette une application en attente (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "app_slug": {"type": "string", "description": "Slug de l'application en attente"},
                "approved": {"type": "boolean", "description": "True pour approuver, False pour rejeter"},
            },
            "required": ["app_slug", "approved"],
        },
    ),
    Tool(
        name="hub_app_docker_scan",
        description="Scanne les conteneurs Docker accessibles depuis le HUB (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    # --- User Management ---
    Tool(
        name="hub_user_list",
        description="Liste les utilisateurs du HUB (pagine, admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Page (default 1)"},
                "per_page": {"type": "integer", "description": "Par page (default 20)"},
                "search": {"type": "string", "description": "Recherche par username ou email"},
            },
            "required": [],
        },
    ),
    Tool(
        name="hub_user_get",
        description="Recupere les details d'un utilisateur par son ID.",
        inputSchema={
            "type": "object",
            "properties": {"user_id": {"type": "integer", "description": "ID utilisateur"}},
            "required": ["user_id"],
        },
    ),
    Tool(
        name="hub_user_create",
        description="Cree un nouvel utilisateur sur le HUB (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "email": {"type": "string"},
                "is_admin": {"type": "boolean", "description": "Role admin global"},
            },
            "required": ["username", "password", "email"],
        },
    ),
    Tool(
        name="hub_user_update",
        description="Met a jour un utilisateur (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "username": {"type": "string"},
                "email": {"type": "string"},
                "is_active": {"type": "boolean"},
            },
            "required": ["user_id"],
        },
    ),
    Tool(
        name="hub_user_delete",
        description="Supprime un utilisateur (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {"user_id": {"type": "integer"}},
            "required": ["user_id"],
        },
    ),
    Tool(
        name="hub_user_set_app_roles",
        description="Assigne des roles d'application a un utilisateur (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "app_roles": {"type": "object", "description": "Mapping {app_slug: role}"},
            },
            "required": ["user_id", "app_roles"],
        },
    ),
    Tool(
        name="hub_user_bulk_create",
        description="Cree plusieurs utilisateurs en masse (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "users": {"type": "array", "items": {"type": "object", "properties": {"username": {"type": "string"}, "password": {"type": "string"}, "email": {"type": "string"}}}},
            },
            "required": ["users"],
        },
    ),
    Tool(
        name="hub_user_bulk_roles",
        description="Met a jour les roles de plusieurs utilisateurs en masse (admin requis).",
        inputSchema={
            "type": "object",
            "properties": {
                "updates": {"type": "array", "items": {"type": "object", "properties": {"user_id": {"type": "integer"}, "role": {"type": "string"}}}},
            },
            "required": ["updates"],
        },
    ),
    # --- Auth & Tokens ---
    Tool(
        name="hub_auth_login",
        description="Authentifie un utilisateur et recupere un token JWT (password grant).",
        inputSchema={
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
            "required": ["username", "password"],
        },
    ),
    Tool(
        name="hub_auth_me",
        description="Recupere les informations de l'utilisateur courant via le token M2M.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="hub_auth_get_m2m_token",
        description="Obtient un token M2M pour l'application courante (client_credentials).",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="hub_auth_get_jwks",
        description="Recupere le JWKS (JSON Web Key Set) du HUB pour valider les tokens JWT.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="hub_auth_token_introspect",
        description="Introspecte un token JWT (RFC 7662, admin ou SA requis).",
        inputSchema={
            "type": "object",
            "properties": {"token": {"type": "string", "description": "Token JWT a introspecter"}},
            "required": ["token"],
        },
    ),
    # --- Backup & Restore ---
    Tool(name="hub_backup_list", description="Liste les backups d'une application (SA ou admin).", inputSchema={"type": "object", "properties": {"app_slug": {"type": "string"}}, "required": ["app_slug"]}),
    Tool(name="hub_backup_get_latest", description="Dernier backup d'une application.", inputSchema={"type": "object", "properties": {"app_slug": {"type": "string"}}, "required": ["app_slug"]}),
    Tool(name="hub_backup_download", description="Telecharge un backup ZIP (SA ou admin).", inputSchema={"type": "object", "properties": {"app_slug": {"type": "string"}, "backup_id": {"type": "integer"}}, "required": ["app_slug", "backup_id"]}),
    Tool(name="hub_backup_config_get", description="Lit la config de backup d'une app (admin).", inputSchema={"type": "object", "properties": {"app_slug": {"type": "string"}}, "required": ["app_slug"]}),
    Tool(name="hub_backup_config_update", description="Modifie la config de backup (admin).", inputSchema={"type": "object", "properties": {"app_slug": {"type": "string"}, "config": {"type": "object"}}, "required": ["app_slug", "config"]}),
    Tool(name="hub_backup_delete", description="Supprime un backup (admin).", inputSchema={"type": "object", "properties": {"app_slug": {"type": "string"}, "backup_id": {"type": "integer"}}, "required": ["app_slug", "backup_id"]}),
    Tool(name="hub_backup_restore", description="Restaure depuis un backup (admin).", inputSchema={"type": "object", "properties": {"app_slug": {"type": "string"}, "backup_id": {"type": "integer"}}, "required": ["app_slug", "backup_id"]}),
    Tool(name="hub_backup_stats", description="Statistiques globales des backups (admin).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_backup_orphans_list", description="Liste les backups orphelins (admin).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_backup_trigger", description="Declenche un backup manuel pour une application (POST /api/apps/{slug}/backup/trigger, admin).", inputSchema={"type": "object", "properties": {"app_slug": {"type": "string", "description": "Slug de l'application a backuper"}}, "required": ["app_slug"]}),
    # --- Messages ---
    Tool(name="hub_message_send", description="Envoie un message (cible ou broadcast, admin).", inputSchema={"type": "object", "properties": {"title": {"type": "string"}, "target_usernames": {"type": "array", "items": {"type": "string"}}, "body": {"type": "string"}, "priority": {"type": "string", "enum": ["info", "warning", "urgent"]}}, "required": ["title", "target_usernames"]}),
    Tool(name="hub_message_list", description="Liste les messages (admin, pagine).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_message_my_list", description="Mes messages (utilisateur courant).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_message_my_unread_count", description="Nombre de messages non lus.", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_message_read", description="Marque un message comme lu.", inputSchema={"type": "object", "properties": {"message_id": {"type": "integer"}}, "required": ["message_id"]}),
    Tool(name="hub_message_stats", description="Statistiques des messages (admin).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_message_m2m_send", description="Envoie un message M2M.", inputSchema={"type": "object", "properties": {"title": {"type": "string"}, "target_usernames": {"type": "array", "items": {"type": "string"}}, "body": {"type": "string"}, "priority": {"type": "string"}}, "required": ["title", "target_usernames"]}),
    # --- Audit ---
    Tool(name="hub_audit_logs", description="Logs d'audit (pagine, filtrable).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_audit_sessions", description="Sessions actives (admin).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_audit_sessions_history", description="Historique des sessions.", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_audit_stats", description="Statistiques globales (admin).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_audit_errors", description="Liste des erreurs (admin).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_audit_errors_stats", description="Statistiques d'erreurs (admin).", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_audit_error_detail", description="Detail d'une erreur avec stack trace.", inputSchema={"type": "object", "properties": {"error_id": {"type": "integer"}}, "required": ["error_id"]}),
    Tool(name="hub_audit_errors_acknowledge", description="Acquitter toutes les erreurs.", inputSchema={"type": "object", "properties": {}, "required": []}),
    # --- Docs ---
    Tool(name="hub_docs_get", description="Documentation d'integration (full ou section).", inputSchema={"type": "object", "properties": {"section": {"type": "string"}}, "required": []}),
    Tool(name="hub_docs_sections", description="Liste les sections de documentation.", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_changelog_get", description="Changelog (filtrable par version).", inputSchema={"type": "object", "properties": {"since": {"type": "string"}, "latest": {"type": "boolean"}, "format": {"type": "string"}}, "required": []}),
    Tool(name="hub_changelog_diff", description="Diff entre deux versions.", inputSchema={"type": "object", "properties": {"from_version": {"type": "string"}}, "required": ["from_version"]}),
    # --- Discovery ---
    Tool(name="hub_discover_services", description="Decouvre les services partages via le Hub.", inputSchema={"type": "object", "properties": {}, "required": []}),
    Tool(name="hub_call_service", description="Appelle un endpoint d'un service decouvert.", inputSchema={"type": "object", "properties": {"service_slug": {"type": "string"}, "endpoint": {"type": "string"}, "method": {"type": "string", "default": "GET"}, "body": {"type": "object", "description": "Corps JSON pour POST/PATCH"}}, "required": ["service_slug", "endpoint"]}),
    # --- Admin ---
    Tool(name="hub_admin_settings", description="Lit un parametre du HUB par sa cle (GET /api/settings/{key}). Seule la cle 'account_requests_enabled' est publique ; les autres necessitent un token admin.", inputSchema={"type": "object", "properties": {"key": {"type": "string", "description": "Cle du parametre (ex: account_requests_enabled)"}}, "required": ["key"]}),
    Tool(name="hub_admin_ports_status", description="Statut du pool de ports (admin).", inputSchema={"type": "object", "properties": {}, "required": []}),
]

# ============================================================
# HANDLER DISPATCH
# ============================================================

HANDLERS = {
    "hub_health": lambda args: hub_client.call_hub_endpoint("/api/health", method="GET"),
    "hub_config": lambda args: hub_client.call_hub_endpoint("/api/config/hub-host", method="GET"),
    "hub_system_time": lambda args: hub_client.call_hub_endpoint("/api/system/time", method="GET"),
    "hub_raw_call": lambda args: hub_client.call_hub_endpoint(
        args.get("path", args.get("endpoint", "/api/health")),
        method=args.get("method", "GET"),
        json=args.get("body"),
    ),
    # --- App Management ---
    "hub_app_list": lambda args: hub_client.call_hub_endpoint(
        "/api/apps/", method="GET",
        params={k: v for k, v in args.items() if v is not None},
    ),
    "hub_app_get": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_id']}", method="GET"),
    "hub_app_create": lambda args: hub_client.call_hub_endpoint("/api/apps/", method="POST", json={"slug": args["slug"], "name": args["name"], "description": args.get("description", ""), "is_shared_service": args.get("is_shared_service", False)}),
    "hub_app_update": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_id']}", method="PATCH", json={k: v for k, v in args.items() if k != "app_id"}),
    "hub_app_delete": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_id']}", method="DELETE"),
    "hub_app_toggle_active": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_id']}/toggle-active", method="PATCH"),
    "hub_app_register": lambda args: _handle_register(args),
    "hub_app_get_credentials": lambda args: _handle_get_credentials(args),
    "hub_app_regenerate_secret": lambda args: _handle_regenerate_secret(args),
    "hub_app_set_users": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_id']}/users", method="POST", json=args["user_ids"]),
    "hub_app_toggle_shared": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_id']}/shared", method="PUT", params={"is_shared": args["shared"]}),
    "hub_app_approve": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_slug']}/approve", method="POST", json={"approve": args["approved"]}),
    "hub_app_docker_scan": lambda args: hub_client.call_hub_endpoint("/api/apps/docker/scan", method="GET"),
    # --- User Management ---
    "hub_user_list": lambda args: hub_client.call_hub_endpoint(
        "/api/users/", method="GET",
        params={k: v for k, v in args.items() if v is not None},
    ),
    "hub_user_get": lambda args: hub_client.call_hub_endpoint(f"/api/users/{args['user_id']}", method="GET"),
    "hub_user_create": lambda args: hub_client.call_hub_endpoint("/api/users/", method="POST", json={k: v for k, v in args.items()}),
    "hub_user_update": lambda args: hub_client.call_hub_endpoint(f"/api/users/{args['user_id']}", method="PATCH", json={k: v for k, v in args.items() if k != "user_id"}),
    "hub_user_delete": lambda args: hub_client.call_hub_endpoint(f"/api/users/{args['user_id']}", method="DELETE"),
    "hub_user_set_app_roles": lambda args: _handle_user_set_app_roles(args),
    "hub_user_bulk_create": lambda args: hub_client.call_hub_endpoint("/api/users/bulk/create", method="POST", json={"users": args["users"]}),
    "hub_user_bulk_roles": lambda args: hub_client.call_hub_endpoint("/api/users/bulk/roles", method="POST", json=args["updates"]),
    # --- Auth & Tokens ---
    "hub_auth_login": lambda args: hub_client.call_hub_endpoint("/api/auth/token", method="POST", data={"grant_type": "password", "username": args["username"], "password": args["password"]}),
    "hub_auth_me": lambda args: hub_client.call_hub_endpoint("/api/auth/me", method="GET"),
    "hub_auth_get_m2m_token": lambda args: _handle_get_m2m_token(args),
    "hub_auth_get_jwks": lambda args: _handle_get_jwks(args),
    "hub_auth_token_introspect": lambda args: hub_client.call_hub_endpoint("/api/auth/token/introspect", method="POST", data={"token": args["token"]}),
    # --- Backup & Restore ---
    "hub_backup_list": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_slug']}/backup", method="GET"),
    "hub_backup_get_latest": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_slug']}/backup/latest", method="GET"),
    "hub_backup_download": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_slug']}/backup/{args['backup_id']}/export", method="GET"),
    "hub_backup_config_get": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_slug']}/backup/config", method="GET"),
    "hub_backup_config_update": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_slug']}/backup/config", method="PUT", json=args["config"]),
    "hub_backup_delete": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_slug']}/backup/{args['backup_id']}", method="DELETE"),
    "hub_backup_restore": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_slug']}/backup/{args['backup_id']}/restore", method="POST"),
    "hub_backup_stats": lambda args: hub_client.call_hub_endpoint("/api/admin/backups/stats", method="GET"),
    "hub_backup_orphans_list": lambda args: hub_client.call_hub_endpoint("/api/admin/backups/orphans", method="GET"),
    "hub_backup_trigger": lambda args: hub_client.call_hub_endpoint(f"/api/apps/{args['app_slug']}/backup/trigger", method="POST"),
    # --- Messages ---
    "hub_message_send": lambda args: hub_client.call_hub_endpoint("/api/messages/send", method="POST", json={k: v for k, v in args.items()}),
    "hub_message_list": lambda args: hub_client.call_hub_endpoint("/api/messages/", method="GET"),
    "hub_message_my_list": lambda args: hub_client.call_hub_endpoint("/api/messages/me", method="GET"),
    "hub_message_my_unread_count": lambda args: hub_client.call_hub_endpoint("/api/messages/me/unread-count", method="GET"),
    "hub_message_read": lambda args: hub_client.call_hub_endpoint(f"/api/messages/{args['message_id']}/read", method="POST"),
    "hub_message_stats": lambda args: hub_client.call_hub_endpoint("/api/messages/stats", method="GET"),
    "hub_message_m2m_send": lambda args: hub_client.call_hub_endpoint("/api/messages/m2m/send", method="POST", json={k: v for k, v in args.items()}),
    # --- Audit ---
    "hub_audit_logs": lambda args: hub_client.call_hub_endpoint("/api/audit/logs", method="GET"),
    "hub_audit_sessions": lambda args: hub_client.call_hub_endpoint("/api/audit/sessions/active", method="GET"),
    "hub_audit_sessions_history": lambda args: hub_client.call_hub_endpoint("/api/audit/sessions/history", method="GET"),
    "hub_audit_stats": lambda args: hub_client.call_hub_endpoint("/api/audit/stats", method="GET"),
    "hub_audit_errors": lambda args: hub_client.call_hub_endpoint("/api/audit/errors", method="GET"),
    "hub_audit_errors_stats": lambda args: hub_client.call_hub_endpoint("/api/audit/errors/stats", method="GET"),
    "hub_audit_error_detail": lambda args: hub_client.call_hub_endpoint(f"/api/audit/errors/{args['error_id']}", method="GET"),
    "hub_audit_errors_acknowledge": lambda args: hub_client.call_hub_endpoint("/api/audit/errors/acknowledge", method="POST"),
    # --- Docs ---
    "hub_docs_get": lambda args: hub_client.call_hub_endpoint(f"/api/docs/integration?section={args['section']}" if args.get('section') else "/api/docs/integration", method="GET"),
    "hub_docs_sections": lambda args: hub_client.call_hub_endpoint("/api/docs/integration/sections", method="GET"),
    "hub_changelog_get": lambda args: hub_client.call_hub_endpoint("/api/docs/changelog", method="GET"),
    "hub_changelog_diff": lambda args: hub_client.call_hub_endpoint(f"/api/docs/changelog/diff?from_version={args['from_version']}", method="GET"),
    # --- Discovery ---
    "hub_discover_services": lambda args: _handle_discover_services(args),
    "hub_call_service": lambda args: hub_client.call_discovered_service(args["service_slug"], args["endpoint"], method=args.get("method", "GET"), json=args.get("body")),
    # --- Admin ---
    "hub_admin_settings": lambda args: hub_client.call_hub_endpoint(f"/api/settings/{args['key']}", method="GET"),
    "hub_admin_ports_status": lambda args: hub_client.call_hub_endpoint("/api/apps/admin/ports/status", method="GET"),
}


# ============================================================
# HELPERS
# ============================================================


async def _handle_register(args):
    """Wrapper pour hub_client.register()."""
    ok = await hub_client.register()
    if ok:
        return {"success": True, "message": "Application enregistree aupres du Hub"}
    return {"success": False, "error": "Echec de l'enregistrement"}


async def _handle_get_credentials(args):
    """Lit les credentials locales sans exposer le secret."""
    if hub_client.is_registered and hub_client.credentials:
        return {
            "client_id": hub_client.credentials.client_id,
            "has_secret": bool(hub_client.credentials.client_secret),
            "has_token": hub_client.credentials.access_token is not None,
        }
    return {"error": "Application non enregistree, pas de credentials locales"}


async def _handle_regenerate_secret(args):
    """Regenere le client secret si l'app est enregistree."""
    if hub_client.is_registered:
        return await hub_client._recover_credentials()
    return {"error": "App non enregistree"}


async def _handle_get_m2m_token(args):
    token = await hub_client.get_m2m_token()
    if token:
        return {"access_token": token, "message": "Token M2M obtenu"}
    return {"error": "Impossible d'obtenir un token M2M"}


async def _handle_get_jwks(args):
    jwks = await hub_client.fetch_jwks()
    if jwks:
        return jwks
    return {"error": "Impossible de recuperer le JWKS"}


async def _handle_discover_services(args):
    services = await hub_client.discover_services()
    result = {}
    for slug, svc in services.items():
        result[slug] = {"name": svc.name, "api_url": svc.api_url, "is_healthy": svc.is_healthy}
    return result


async def _handle_user_set_app_roles(args):
    """Convertit un dict {app_slug: role} en format API assignments [{app_id, role}]."""
    app_roles = args.get("app_roles", {})
    # Charger toutes les apps pour résoudre slug → id
    try:
        apps = await hub_client.call_hub_endpoint("/api/apps/", method="GET", params={"per_page": 100})
    except Exception:
        apps = []
    slug_to_id = {a["slug"]: a["id"] for a in apps if "slug" in a}
    assignments = []
    for slug, role in app_roles.items():
        app_id = slug_to_id.get(slug)
        if app_id is None:
            try:
                app_id = int(slug)
            except ValueError:
                return {"error": f"Application '{slug}' introuvable"}
        assignments.append({"app_id": app_id, "role": role})
    if not assignments:
        return {"error": "Aucune application valide dans app_roles"}
    return await hub_client.call_hub_endpoint(
        f"/api/users/{args['user_id']}/apps", method="POST",
        json={"assignments": assignments}
    )



# ============================================================
# REGISTRATION
# ============================================================

def register_all_tools(server):
    """Enregistre tous les tools et leurs handlers sur le serveur MCP."""

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = HANDLERS.get(name)
        if handler is None:
            return [TextContent(type="text", text=f"Tool inconnu: {name}")]

        try:
            result = await handler(arguments)
            text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            text = json.dumps({"error": str(e), "tool": name}, indent=2)

        return [TextContent(type="text", text=text)]
