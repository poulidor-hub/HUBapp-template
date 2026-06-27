"""
Application FastAPI principale.
Template pour applications connectées au Hub.

Les routes métier sont organisées dans le package routes/ :
- routes/items.py        : CRUD items (exemple)
- routes/preferences.py  : Préférences utilisateur
- routes/m2m.py          : M2M et découverte de services
- routes/test_data.py    : Données de test (backup)
- routes/backup.py       : Backup / Restore
- routes/docs.py         : Documentation / Changelog
- routes/tests.py        : Tests des services Hub
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from typing import Optional
import logging
import asyncio
import os

from config import get_settings, APP_VERSION
from database import init_db, close_db, apply_migrations
from hub_client import hub_client
from outbox import outbox_service
from hub_auth import (
    hub_auth,
    get_current_user,
    require_role,
    require_service_account,
    TokenPayload
)
from schemas import UserInfo

# Routeurs
from routes.docs import router as docs_router
from routes.backup import router as backup_router
from routes.tests import router as tests_router
from routes.items import router as items_router
from routes.preferences import router as preferences_router
from routes.m2m import router as m2m_router
from routes.test_data import router as test_data_router

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


async def hub_reconnection_loop():
    """
    Boucle de reconnexion automatique au Hub.
    Tourne en arrière-plan et tente de se reconnecter périodiquement
    si l'application n'est pas enregistrée, si le token M2M est indisponible
    pour une app partagée, ou si l'auth Hub est indisponible.
    """
    RECONNECT_INTERVAL = 15  # secondes entre les tentatives
    
    while True:
        try:
            await asyncio.sleep(RECONNECT_INTERVAL)
            
            # Cas 1: Application non enregistrée
            if not hub_client.is_registered:
                logger.info("🔄 Hub non enregistré, tentative de reconnexion...")
                registered = await hub_client.register()
                if registered:
                    logger.info("✅ Enregistrement Hub réussi!")
                    await hub_auth.initialize()
            
            # Cas 2: Token M2M indisponible pour les apps partagées.
            m2m_ok = True
            if settings.IS_SHARED and hub_client.is_registered:
                token = await hub_client.get_m2m_token()
                m2m_ok = token is not None
                if token:
                    logger.info("✅ Token M2M disponible, boucle de reconnexion terminée")
                    break
            
            # Cas 3: JWKS indisponible (Hub a peut-être redémarré)
            if not hub_auth._jwks_available or not hub_auth._hub_reachable:
                logger.info("🔄 JWKS/Hub indisponible, tentative de restauration...")
                await hub_auth.initialize()
                if hub_auth._jwks_available:
                    logger.info("✅ Connexion JWKS restaurée!")
            
            if (
                hub_client.is_registered
                and hub_auth._jwks_available
                and hub_auth._hub_reachable
                and m2m_ok
            ):
                logger.info("✅ Connexion Hub disponible, boucle de reconnexion terminée")
                break
            
        except asyncio.CancelledError:
            logger.info("🛑 Arrêt de la boucle de reconnexion Hub")
            break
        except Exception as e:
            logger.debug(f"Erreur dans la boucle de reconnexion: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestion du cycle de vie de l'application.
    - Démarrage: enregistrement Hub + init DB + découverte services
    - Arrêt: fermeture connexions
    """
    startup_time = datetime.now(timezone.utc)
    logger.info(f"🚀 Démarrage de l'application '{settings.APP_SLUG}'...")
    
    # 1. Auto-enregistrement auprès du Hub
    registered = await hub_client.register()
    if not registered:
        logger.warning("⚠️ Impossible de s'enregistrer auprès du Hub. Mode dégradé.")
    
    # 2. Initialisation de l'authentification Hub
    await hub_auth.initialize()
    
    # 3. Initialisation de la base de données
    try:
        await init_db()
        await apply_migrations()
        logger.info("✅ Base de données initialisée")
        await apply_migrations()
    except Exception as e:
        logger.error(f"❌ Erreur init DB: {e}")
    
    # 4. Découverte des services partagés (si IS_SHARED actif)
    discovered_count = 0
    m2m_ok = not settings.IS_SHARED
    if registered and settings.IS_SHARED:
        try:
            services = await hub_client.discover_services()
            discovered_count = len(services)
            m2m_ok = discovered_count > 0 or (await hub_client.get_m2m_token() is not None)
            if discovered_count > 0:
                logger.info(f"🔍 {discovered_count} service(s) partagé(s) découvert(s)")
            else:
                logger.info("🔍 Aucun service partagé découvert (IS_SHARED non activé ou aucun service disponible)")
        except Exception as e:
            logger.warning(f"⚠️ Erreur découverte services: {e}")
    elif registered:
        logger.info("🔍 Découverte M2M ignorée (IS_SHARED=false)")
    
    # 5. Stocker les infos de démarrage dans app.state
    app.state.startup_time = startup_time
    app.state.is_registered = registered
    app.state.discovered_services_count = discovered_count
    app.state.hub_reconnect_task = None
    
    # 6. Démarrer la tâche de reconnexion automatique en arrière-plan
    if not registered or not hub_auth._jwks_available or not m2m_ok:
        app.state.hub_reconnect_task = asyncio.create_task(hub_reconnection_loop())
        logger.info("🔄 Tâche de reconnexion Hub démarrée en arrière-plan")
    
    # 7. Démarrer le worker outbox (livraison garantie)
    async def _outbox_auth_provider(slug: str) -> dict:
        token = await hub_client.get_m2m_token()
        if token:
            return {"Authorization": f"Bearer {token}", "X-Slug": slug}
        return {}

    outbox_service.set_auth_provider(_outbox_auth_provider)
    outbox_service.start_worker()
    app.state.outbox_worker_active = True
    logger.info("📦 Worker outbox démarré")
    
    startup_duration = (datetime.now(timezone.utc) - startup_time).total_seconds()
    logger.info(f"✅ Application prête sur {settings.api_url} (démarrage en {startup_duration:.2f}s)")
    
    yield  # L'application tourne
    
    # Arrêt
    logger.info("🛑 Arrêt de l'application...")
    
    reconnect_task = getattr(app.state, 'hub_reconnect_task', None)
    if reconnect_task and not reconnect_task.done():
        reconnect_task.cancel()
        try:
            await reconnect_task
        except asyncio.CancelledError:
            pass
    
    await outbox_service.stop_worker()
    await outbox_service.cleanup_old_messages()
    
    await hub_client.close()
    await close_db()


# Création de l'application
app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS - Configurer les origines autorisées
# En prod, définir CORS_ORIGINS dans .env (ex: "http://localhost:4250,https://monapp.fr")
cors_origins = os.environ.get("CORS_ORIGINS", "").split(",") if os.environ.get("CORS_ORIGINS") else [
    f"http://localhost:{settings.FRONTEND_PORT}",
    f"http://127.0.0.1:{settings.FRONTEND_PORT}",
    f"http://{settings.app_host}:{settings.FRONTEND_PORT}",
    f"https://localhost:{settings.FRONTEND_PORT + 1}",
    f"https://127.0.0.1:{settings.FRONTEND_PORT + 1}",
    f"https://{settings.app_host}:{settings.FRONTEND_PORT + 1}",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Inclusion des routeurs
app.include_router(docs_router)
app.include_router(backup_router)
if settings.ENABLE_DEMO_ENDPOINTS:
    app.include_router(tests_router)
    app.include_router(test_data_router)
    logger.info("🧪 Endpoints démo activés (ENABLE_DEMO_ENDPOINTS=true)")
app.include_router(items_router)
app.include_router(preferences_router)
app.include_router(m2m_router)


# ============================================================
# ENDPOINTS PUBLICS (sans authentification)
# ============================================================

@app.get("/api/health", tags=["Public"])
async def health_check():
    """Health check - toujours accessible."""
    hub_registered = getattr(app.state, 'is_registered', False)
    
    return {
        "status": "healthy",
        "app": settings.APP_SLUG,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hub_connected": hub_registered,
    }


@app.get("/api/health/detailed", tags=["Public"])
async def health_check_detailed():
    """
    Health check détaillé avec informations sur les dépendances.
    Utile pour le monitoring avancé et le debugging.
    """
    now = datetime.now(timezone.utc)
    startup_time = getattr(app.state, 'startup_time', None)
    uptime_seconds = (now - startup_time).total_seconds() if startup_time else None
    
    # État de la connexion Hub
    hub_registered = hub_client.is_registered
    hub_can_authenticate = bool(hub_auth._jwks_available)
    m2m_token_available = None
    if settings.IS_SHARED and hub_registered:
        try:
            token = await hub_client.get_m2m_token()
            m2m_token_available = token is not None
        except Exception:
            pass
    
    # Services découverts
    discovered_services = []
    if settings.IS_SHARED:
        discovered_services = await hub_client.list_discovered_services()
    services_cache_age = None
    if hub_client._discovered_services_fetched_at:
        services_cache_age = (now - hub_client._discovered_services_fetched_at).total_seconds()
    
    # Statut du cache JWKS
    jwks_cache_status = hub_auth.get_jwks_cache_status()
    
    # Statistiques outbox
    outbox_stats = await outbox_service.get_stats()
    
    return {
        "status": "healthy" if hub_registered else "degraded",
        "app": {
            "slug": settings.APP_SLUG,
            "name": settings.APP_NAME,
            "version": APP_VERSION,
        },
        "timestamp": now.isoformat(),
        "uptime_seconds": uptime_seconds,
        "hub": {
            "connected": hub_registered,
            "can_authenticate": hub_can_authenticate,
            "m2m_token_available": m2m_token_available,
            "api_url": settings.hub_api_url,
        },
        "services": {
            "discovered_count": len(discovered_services),
            "cache_age_seconds": services_cache_age,
            "services": [
                {"slug": s.slug, "status": s.status, "is_healthy": s.is_healthy}
                for s in discovered_services[:10]
            ]
        },
        "outbox": outbox_stats,
        "jwks_cache": jwks_cache_status,
        "config": {
            "is_shared": settings.IS_SHARED,
            "debug": settings.DEBUG,
        }
    }


@app.get("/api/health/hub/jwks", tags=["Public"])
async def health_hub_jwks():
    """
    Statut du cache JWKS (mémoire + disque).
    
    Permet de diagnostiquer l'état du système d'authentification :
    - Cache mémoire : clés JWKS en RAM (TTL 30 min)
    - Cache persistant : clés sauvegardées sur disque (max 7 jours)
    - Fallback PEM : clé publique statique
    
    Returns:
        dict avec le statut détaillé du cache JWKS
    """
    return hub_auth.get_jwks_cache_status()


@app.post("/api/health/hub/jwks/refresh", tags=["Admin"])
async def health_hub_jwks_refresh(user: TokenPayload = Depends(require_role("admin"))):
    """
    Force le rafraîchissement du cache JWKS.
    Réservé aux admins pour éviter les abus (rate limiting implicite).
    
    Utile pour :
    - Forcer la récupération des clés après rotation
    - Tester la connectivité avec le Hub
    - Rétablir le cache après une indisponibilité du Hub
    
    Returns:
        dict avec le résultat du rafraîchissement
    """
    return await hub_auth.refresh_jwks_cache()


@app.get("/api/version", tags=["Public"])
async def get_version():
    """
    Retourne la version actuelle de l'application.
    Utile pour le monitoring et la vérification de déploiement.
    """
    return {
        "version": APP_VERSION,
        "app": settings.APP_SLUG,
        "name": settings.APP_NAME
    }


@app.get("/api/config", tags=["Public"])
async def get_public_config():
    """Configuration publique pour le frontend."""
    return {
        "app_slug": settings.APP_SLUG,
        "app_name": settings.APP_NAME,
        "hub_frontend_url": settings.hub_frontend_url,
        "hub_api_url": settings.hub_api_url,
        "api_url": settings.api_url,
    }


@app.get("/api/public", tags=["Public"])
async def public_endpoint():
    """
    Endpoint public - accessible sans authentification.
    Utile pour les données publiques, pages d'accueil, etc.
    """
    return {
        "message": "Cet endpoint est accessible à tous",
        "authenticated": False
    }


# ============================================================
# ENDPOINTS PROTÉGÉS (authentification requise)
# ============================================================

@app.get("/api/protected", tags=["Protected"])
async def protected_endpoint(user: TokenPayload = Depends(get_current_user)):
    """
    Endpoint protégé - nécessite un token valide.
    Accessible à tous les utilisateurs authentifiés, quel que soit leur rôle.
    """
    return {
        "message": "Bienvenue ! Vous êtes authentifié.",
        "user": user.sub,
        "app_role": user.get_app_role(settings.APP_SLUG),
        "token_type": user.token_type
    }


@app.get("/api/me", response_model=UserInfo, tags=["Protected"])
async def get_current_user_info(user: TokenPayload = Depends(get_current_user)):
    """Retourne les informations de l'utilisateur connecté."""
    return UserInfo(
        username=user.sub,
        app_role=user.get_app_role(settings.APP_SLUG),
        is_service_account=user.is_service_account()
    )


# ============================================================
# ENDPOINTS PAR RÔLE (hiérarchie: viewer < user < manager < admin)
# ============================================================

@app.get("/api/viewer-only", tags=["Roles"])
async def viewer_endpoint(user: TokenPayload = Depends(require_role("viewer"))):
    """
    Endpoint viewer+ - accessible aux rôles viewer, user, manager, admin.
    Niveau minimum pour accéder à l'application.
    """
    return {
        "message": "Accès viewer accordé",
        "user": user.sub,
        "role": user.get_app_role(settings.APP_SLUG)
    }


@app.get("/api/user-only", tags=["Roles"])
async def user_endpoint(user: TokenPayload = Depends(require_role("user"))):
    """
    Endpoint user+ - accessible aux rôles user, manager, admin.
    Peut créer et modifier ses propres données.
    """
    return {
        "message": "Accès user accordé",
        "user": user.sub,
        "role": user.get_app_role(settings.APP_SLUG)
    }


@app.get("/api/manager-only", tags=["Roles"])
async def manager_endpoint(user: TokenPayload = Depends(require_role("manager"))):
    """
    Endpoint manager+ - accessible aux rôles manager et admin.
    Peut gérer les données de tous les utilisateurs.
    """
    return {
        "message": "Accès manager accordé",
        "user": user.sub,
        "role": user.get_app_role(settings.APP_SLUG)
    }


@app.get("/api/admin-only", tags=["Roles"])
async def admin_endpoint(user: TokenPayload = Depends(require_role("admin"))):
    """
    Endpoint admin uniquement - accès complet.
    Peut tout faire dans l'application.
    """
    return {
        "message": "Accès admin accordé",
        "user": user.sub,
        "role": user.get_app_role(settings.APP_SLUG)
    }


@app.get("/api/service-only", tags=["Roles"])
async def service_endpoint(user: TokenPayload = Depends(require_service_account())):
    """
    Endpoint réservé aux service accounts (M2M).
    Pour les communications inter-services.
    """
    return {
        "message": "Accès service account accordé",
        "service": user.sub,
        "token_type": user.token_type
    }


# ============================================================
# ENDPOINTS OUTBOX (administration)
# ============================================================

@app.get("/api/outbox/stats", tags=["Admin"])
async def outbox_stats(user: TokenPayload = Depends(require_role("admin"))):
    """Statistiques de la file outbox."""
    return await outbox_service.get_stats()


@app.post("/api/outbox/{msg_id}/retry", tags=["Admin"])
async def outbox_retry(
    msg_id: int,
    user: TokenPayload = Depends(require_role("admin")),
):
    """Force le retry d'un message outbox en échec."""
    success = await outbox_service.retry_failed_message(msg_id)
    if success:
        return {"success": True, "message": f"Message #{msg_id} remis en file d'attente"}
    raise HTTPException(status_code=404, detail=f"Message #{msg_id} introuvable ou pas en échec")


@app.post("/api/outbox/cleanup", tags=["Admin"])
async def outbox_cleanup(user: TokenPayload = Depends(require_role("admin"))):
    """Purge les vieux messages outbox (delivered > 7j, failed > 30j)."""
    await outbox_service.cleanup_old_messages()
    return {"success": True, "message": "Nettoyage effectué"}


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
