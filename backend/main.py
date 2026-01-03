"""
Application FastAPI principale avec endpoints de démonstration.
Template pour applications connectées au Hub.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime
import logging

from config import get_settings
from database import get_db, init_db, close_db
from hub_client import hub_client
from hub_auth import (
    hub_auth, 
    get_current_user, 
    get_optional_user,
    require_role,
    require_any_role,
    require_service_account,
    TokenPayload
)
from models import Item, UserPreference
from schemas import (
    ItemCreate, ItemUpdate, ItemResponse,
    UserPreferenceUpdate, UserPreferenceResponse,
    UserInfo, MessageResponse, PaginatedResponse
)

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestion du cycle de vie de l'application.
    - Démarrage: enregistrement Hub + init DB
    - Arrêt: fermeture connexions
    """
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
        logger.info("✅ Base de données initialisée")
    except Exception as e:
        logger.error(f"❌ Erreur init DB: {e}")
    
    logger.info(f"✅ Application prête sur {settings.api_url}")
    
    yield  # L'application tourne
    
    # Arrêt
    logger.info("🛑 Arrêt de l'application...")
    await close_db()


# Création de l'application
app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS - Autoriser le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En prod, restreindre aux URLs connues
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ENDPOINTS PUBLICS (sans authentification)
# ============================================================

@app.get("/api/health", tags=["Public"])
async def health_check():
    """Health check - toujours accessible."""
    return {
        "status": "healthy",
        "app": settings.APP_SLUG,
        "timestamp": datetime.utcnow().isoformat()
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
        roles=user.roles,
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
        "role": user.get_app_role(settings.APP_SLUG),
        "level": "viewer (lecture seule)"
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
        "role": user.get_app_role(settings.APP_SLUG),
        "level": "user (lecture/écriture)"
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
        "role": user.get_app_role(settings.APP_SLUG),
        "level": "manager (gestion)"
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
        "role": user.get_app_role(settings.APP_SLUG),
        "level": "admin (tous droits)"
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
# ENDPOINTS M2M (Machine-to-Machine)
# ============================================================

@app.get("/api/m2m/status", tags=["M2M"])
async def m2m_status():
    """
    Statut de la connexion M2M avec le Hub.
    Retourne si l'app est enregistrée et peut obtenir des tokens.
    """
    is_registered = hub_client.is_registered
    token = None
    token_error = None
    
    if is_registered:
        try:
            token = await hub_client.get_m2m_token()
        except Exception as e:
            token_error = str(e)
    
    return {
        "registered": is_registered,
        "client_id": hub_client.credentials.client_id if hub_client.credentials else None,
        "can_get_token": token is not None,
        "token_preview": f"{token[:20]}...{token[-10:]}" if token else None,
        "error": token_error
    }


@app.post("/api/m2m/test-call", tags=["M2M"])
async def test_m2m_call(
    target_url: str,
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Test d'appel M2M vers un autre service.
    Requiert admin car c'est un outil de debug.
    """
    import httpx
    
    token = await hub_client.get_m2m_token()
    if not token:
        return {"success": False, "error": "Impossible d'obtenir un token M2M"}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                target_url,
                headers={"Authorization": f"Bearer {token}"}
            )
            return {
                "success": True,
                "status_code": response.status_code,
                "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:500]
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
# ============================================================
# CRUD ITEMS (exemple avec base de données)
# ============================================================

@app.get("/api/items", response_model=PaginatedResponse, tags=["Items"])
async def list_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: Optional[TokenPayload] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Liste les items.
    - Sans auth: uniquement les items publics
    - Avec auth: items publics + ses propres items
    - Admin: tous les items
    """
    query = select(Item)
    
    if user is None:
        # Non authentifié: uniquement publics
        query = query.where(Item.is_public == True)
    elif user.get_app_role(settings.APP_SLUG) == "admin" or user.has_global_role("admin"):
        # Admin: tous les items
        pass
    else:
        # Authentifié: publics + les siens
        query = query.where(
            (Item.is_public == True) | (Item.owner == user.sub)
        )
    
    # Comptage total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    
    # Pagination
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return PaginatedResponse(
        items=[ItemResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )


@app.post("/api/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED, tags=["Items"])
async def create_item(
    item_data: ItemCreate,
    user: TokenPayload = Depends(require_role("user")),
    db: AsyncSession = Depends(get_db)
):
    """
    Crée un nouvel item.
    Requiert le rôle user minimum.
    """
    item = Item(
        title=item_data.title,
        description=item_data.description,
        is_public=item_data.is_public,
        owner=user.sub
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    
    return ItemResponse.model_validate(item)


@app.get("/api/items/{item_id}", response_model=ItemResponse, tags=["Items"])
async def get_item(
    item_id: int,
    user: Optional[TokenPayload] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupère un item par son ID."""
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item non trouvé")
    
    # Vérifier les droits d'accès
    if not item.is_public:
        if user is None:
            raise HTTPException(status_code=401, detail="Authentification requise")
        if item.owner != user.sub and user.get_app_role(settings.APP_SLUG) != "admin":
            raise HTTPException(status_code=403, detail="Accès non autorisé")
    
    return ItemResponse.model_validate(item)


@app.put("/api/items/{item_id}", response_model=ItemResponse, tags=["Items"])
async def update_item(
    item_id: int,
    item_data: ItemUpdate,
    user: TokenPayload = Depends(require_role("user")),
    db: AsyncSession = Depends(get_db)
):
    """
    Met à jour un item.
    Seul le propriétaire ou un admin peut modifier.
    """
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item non trouvé")
    
    # Vérifier les droits
    is_admin = user.get_app_role(settings.APP_SLUG) == "admin" or user.has_global_role("admin")
    if item.owner != user.sub and not is_admin:
        raise HTTPException(status_code=403, detail="Seul le propriétaire peut modifier")
    
    # Mise à jour des champs fournis
    update_data = item_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    
    await db.flush()
    await db.refresh(item)
    
    return ItemResponse.model_validate(item)


@app.delete("/api/items/{item_id}", response_model=MessageResponse, tags=["Items"])
async def delete_item(
    item_id: int,
    user: TokenPayload = Depends(require_role("user")),
    db: AsyncSession = Depends(get_db)
):
    """
    Supprime un item.
    Seul le propriétaire ou un admin peut supprimer.
    """
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item non trouvé")
    
    # Vérifier les droits
    is_admin = user.get_app_role(settings.APP_SLUG) == "admin" or user.has_global_role("admin")
    if item.owner != user.sub and not is_admin:
        raise HTTPException(status_code=403, detail="Seul le propriétaire peut supprimer")
    
    await db.delete(item)
    
    return MessageResponse(message="Item supprimé", detail=f"Item #{item_id} supprimé avec succès")


# ============================================================
# PRÉFÉRENCES UTILISATEUR
# ============================================================

@app.get("/api/preferences", response_model=UserPreferenceResponse, tags=["Preferences"])
async def get_preferences(
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupère les préférences de l'utilisateur connecté."""
    result = await db.execute(
        select(UserPreference).where(UserPreference.username == user.sub)
    )
    prefs = result.scalar_one_or_none()
    
    if not prefs:
        # Créer des préférences par défaut
        prefs = UserPreference(username=user.sub)
        db.add(prefs)
        await db.flush()
        await db.refresh(prefs)
    
    return UserPreferenceResponse.model_validate(prefs)


@app.put("/api/preferences", response_model=UserPreferenceResponse, tags=["Preferences"])
async def update_preferences(
    prefs_data: UserPreferenceUpdate,
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Met à jour les préférences de l'utilisateur connecté."""
    result = await db.execute(
        select(UserPreference).where(UserPreference.username == user.sub)
    )
    prefs = result.scalar_one_or_none()
    
    if not prefs:
        prefs = UserPreference(username=user.sub)
        db.add(prefs)
    
    # Mise à jour des champs fournis
    update_data = prefs_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prefs, field, value)
    
    await db.flush()
    await db.refresh(prefs)
    
    return UserPreferenceResponse.model_validate(prefs)


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
