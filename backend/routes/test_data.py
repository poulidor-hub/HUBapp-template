"""
Routes pour les données de test.
Données partagées modifiables par tous les utilisateurs authentifiés.
Utilisées principalement pour tester le système de backup/restore.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging

from database import get_db
from hub_auth import require_role, TokenPayload
from models import TestData
from schemas import (
    TestDataCreate, TestDataUpdate, TestDataResponse, TestDataListResponse,
    MessageResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Test Data"])


@router.get("/test-data", response_model=TestDataListResponse)
async def list_test_data(
    category: Optional[str] = Query(None, description="Filtrer par catégorie"),
    db: AsyncSession = Depends(get_db)
):
    """
    Liste toutes les données de test.
    Accessible sans authentification pour visualisation.
    Ces données sont partagées entre tous les utilisateurs.
    """
    query = select(TestData)
    
    if category:
        query = query.where(TestData.category == category)
    
    query = query.order_by(TestData.id)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return TestDataListResponse(
        items=[TestDataResponse.model_validate(item) for item in items],
        total=len(items)
    )


@router.post("/test-data", response_model=TestDataResponse, status_code=status.HTTP_201_CREATED)
async def create_test_data(
    data: TestDataCreate,
    user: TokenPayload = Depends(require_role("user")),
    db: AsyncSession = Depends(get_db)
):
    """
    Crée une nouvelle donnée de test.
    Requiert le rôle user minimum.
    """
    test_data = TestData(
        name=data.name,
        value=data.value,
        category=data.category,
        last_modified_by=user.sub
    )
    db.add(test_data)
    await db.flush()
    await db.refresh(test_data)
    
    return TestDataResponse.model_validate(test_data)


@router.put("/test-data/{data_id}", response_model=TestDataResponse)
async def update_test_data(
    data_id: int,
    data: TestDataUpdate,
    user: TokenPayload = Depends(require_role("user")),
    db: AsyncSession = Depends(get_db)
):
    """
    Met à jour une donnée de test.
    Tous les utilisateurs authentifiés (rôle user+) peuvent modifier.
    """
    result = await db.execute(select(TestData).where(TestData.id == data_id))
    test_data = result.scalar_one_or_none()
    
    if not test_data:
        raise HTTPException(status_code=404, detail="Donnée non trouvée")
    
    # Mise à jour des champs fournis
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(test_data, field, value)
    
    # Mettre à jour le modificateur
    test_data.last_modified_by = user.sub
    
    await db.flush()
    await db.refresh(test_data)
    
    return TestDataResponse.model_validate(test_data)


@router.delete("/test-data/{data_id}", response_model=MessageResponse)
async def delete_test_data(
    data_id: int,
    user: TokenPayload = Depends(require_role("user")),
    db: AsyncSession = Depends(get_db)
):
    """
    Supprime une donnée de test.
    Tous les utilisateurs authentifiés (rôle user+) peuvent supprimer.
    """
    result = await db.execute(select(TestData).where(TestData.id == data_id))
    test_data = result.scalar_one_or_none()
    
    if not test_data:
        raise HTTPException(status_code=404, detail="Donnée non trouvée")
    
    await db.delete(test_data)
    
    return MessageResponse(message="Donnée supprimée", detail=f"Donnée #{data_id} supprimée avec succès")


@router.post("/test-data/seed", response_model=TestDataListResponse)
async def seed_test_data(
    user: TokenPayload = Depends(require_role("user")),
    db: AsyncSession = Depends(get_db)
):
    """
    Initialise des données de test par défaut.
    Utile pour avoir des données à sauvegarder/restaurer.
    """
    # Données de test initiales
    seed_data = [
        {"name": "Serveur Web", "value": "nginx", "category": "infrastructure"},
        {"name": "Base de données", "value": "PostgreSQL 15", "category": "infrastructure"},
        {"name": "Framework Backend", "value": "FastAPI", "category": "stack"},
        {"name": "Framework Frontend", "value": "React", "category": "stack"},
        {"name": "Version Python", "value": "3.11", "category": "stack"},
        {"name": "Environnement", "value": "development", "category": "config"},
        {"name": "Port API", "value": "8000", "category": "config"},
        {"name": "Debug Mode", "value": "true", "category": "config"},
    ]
    
    created = []
    for item in seed_data:
        # Vérifier si existe déjà
        existing = await db.execute(
            select(TestData).where(
                TestData.name == item["name"],
                TestData.category == item["category"]
            )
        )
        if existing.scalar_one_or_none():
            continue
        
        test_data = TestData(
            name=item["name"],
            value=item["value"],
            category=item["category"],
            last_modified_by=user.sub
        )
        db.add(test_data)
        await db.flush()
        await db.refresh(test_data)
        created.append(test_data)
    
    return TestDataListResponse(
        items=[TestDataResponse.model_validate(item) for item in created],
        total=len(created)
    )
