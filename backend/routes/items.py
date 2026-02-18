"""
Routes CRUD pour les items.
Exemple de modèle avec propriétaire et visibilité publique/privée.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import logging

from config import get_settings
from database import get_db
from hub_auth import get_optional_user, require_role, TokenPayload
from models import Item
from schemas import (
    ItemCreate, ItemUpdate, ItemResponse,
    MessageResponse, PaginatedResponse
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api", tags=["Items"])


@router.get("/items", response_model=PaginatedResponse)
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
    elif user.get_app_role(settings.APP_SLUG) == "admin":
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


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
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


@router.get("/items/{item_id}", response_model=ItemResponse)
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


@router.put("/items/{item_id}", response_model=ItemResponse)
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
    
    # Vérifier les droits (seul le rôle applicatif compte)
    is_admin = user.get_app_role(settings.APP_SLUG) == "admin"
    if item.owner != user.sub and not is_admin:
        raise HTTPException(status_code=403, detail="Seul le propriétaire peut modifier")
    
    # Mise à jour des champs fournis
    update_data = item_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    
    await db.flush()
    await db.refresh(item)
    
    return ItemResponse.model_validate(item)


@router.delete("/items/{item_id}", response_model=MessageResponse)
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
    
    # Vérifier les droits (seul le rôle applicatif compte)
    is_admin = user.get_app_role(settings.APP_SLUG) == "admin"
    if item.owner != user.sub and not is_admin:
        raise HTTPException(status_code=403, detail="Seul le propriétaire peut supprimer")
    
    await db.delete(item)
    
    return MessageResponse(message="Item supprimé", detail=f"Item #{item_id} supprimé avec succès")
