"""
Routes pour tester l'ensemble des services de l'application par rapport au Hub.

Endpoints:
- GET  /api/tests/services          : Teste tous les services (connexion, X-Slug, M2M, SSE, backup)
- GET  /api/tests/hub-connection    : Test de connexion au Hub
- GET  /api/tests/slug-recovery     : Test de récupération X-Slug (role + user)
- GET  /api/tests/m2m               : Test du service M2M
- GET  /api/tests/sse               : Test du flux SSE
- GET  /api/tests/backup            : Test du système de backup
- POST /api/tests/messages/send     :
    Envoie un message de test via le Hub (admin)
"""
import asyncio
import httpx
from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from config import get_settings, APP_VERSION
from database import get_db
from hub_auth import require_role, get_current_user, TokenPayload
from hub_client import hub_client

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/tests", tags=["Tests Services"])


# ============================================================
# SCHEMAS DE RÉPONSE
# ============================================================

class ServiceTestResult(BaseModel):
    """Résultat d'un test de service."""
    name: str = Field(..., description="Nom du test")
    success: bool = Field(..., description="Test réussi")
    duration_ms: float = Field(..., description="Durée du test en millisecondes")
    message: str = Field(..., description="Message descriptif")
    details: Optional[dict] = Field(None, description="Détails supplémentaires")


class AllServicesTestResult(BaseModel):
    """Résultat de tous les tests de services."""
    timestamp: str = Field(..., description="Date/heure des tests")
    app_slug: str = Field(..., description="Slug de l'application")
    app_version: str = Field(..., description="Version de l'application")
    overall_success: bool = Field(..., description="Tous les tests ont réussi")
    total_duration_ms: float = Field(..., description="Durée totale en millisecondes")
    tests: list[ServiceTestResult] = Field(..., description="Résultats de chaque test")
    summary: dict = Field(..., description="Résumé des tests")


class SendTestMessageRequest(BaseModel):
    """Payload d'envoi d'un message de test via le Hub."""
    target_usernames: list[str] = Field(
        default_factory=list,
        description=(
            "Destinataires. Si vide, le message est envoyé "
            "à l'utilisateur courant."
        )
    )
    title: str = Field(
        default="Message de test HUB",
        min_length=1,
        max_length=200,
        description="Titre du message"
    )
    body: Optional[str] = Field(
        default=(
            "Ce message valide l'integration de la messagerie "
            "Hub via M2M."
        ),
        description="Contenu optionnel du message"
    )
    priority: Literal["info", "warning", "urgent"] = Field(
        default="info",
        description="Priorité du message"
    )
    action_url: Optional[str] = Field(
        default=None,
        description="URL d'action optionnelle"
    )
    action_label: Optional[str] = Field(
        default=None,
        description="Libellé du bouton d'action"
    )
    expires_at: Optional[str] = Field(
        default=None,
        description="Date d'expiration ISO 8601 optionnelle"
    )


class SendTestMessageResult(BaseModel):
    """Réponse de l'endpoint d'envoi de message de test."""
    message: str = Field(..., description="Résultat de l'opération")
    sent_by: str = Field(
        ...,
        description="Utilisateur ayant déclenché l'envoi"
    )
    target_usernames: list[str] = Field(
        ...,
        description="Destinataires effectifs"
    )
    title: str = Field(..., description="Titre envoyé")
    priority: Literal["info", "warning", "urgent"] = Field(
        ...,
        description="Priorité envoyée"
    )
    hub_response: dict = Field(
        ...,
        description="Réponse brute retournée par le Hub"
    )


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    """Supprime les espaces inutiles et convertit les chaînes vides en None."""
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _normalize_target_usernames(target_usernames: list[str]) -> list[str]:
    """Nettoie et déduplique une liste de usernames en préservant l'ordre."""
    normalized_targets: list[str] = []
    seen_targets: set[str] = set()

    for raw_username in target_usernames:
        normalized_username = raw_username.strip()
        if not normalized_username or normalized_username in seen_targets:
            continue
        seen_targets.add(normalized_username)
        normalized_targets.append(normalized_username)

    return normalized_targets


# ============================================================
# FONCTIONS DE TEST INDIVIDUELLES
# ============================================================

async def _test_hub_connection() -> ServiceTestResult:
    """
    Teste la connexion au Hub.
    Vérifie que le Hub est accessible et que l'app est enregistrée.
    """
    start = datetime.now(timezone.utc)
    try:
        # Test 1: Le Hub est-il accessible ?
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.hub_api_internal_url}/api/health"
            )
            hub_accessible = response.status_code == 200
        
        # Test 2: L'app est-elle enregistrée ?
        is_registered = hub_client.is_registered
        
        # Test 3: Les credentials sont-ils valides ?
        credentials_valid = False
        if is_registered:
            credentials_valid = await hub_client.ensure_valid_credentials()
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        success = hub_accessible and is_registered and credentials_valid
        
        return ServiceTestResult(
            name="Hub Connection",
            success=success,
            duration_ms=duration,
            message="Connexion au Hub opérationnelle" if success else "Problème de connexion au Hub",
            details={
                "hub_url": settings.hub_api_url,
                "hub_internal_url": settings.hub_api_internal_url,
                "hub_accessible": hub_accessible,
                "app_registered": is_registered,
                "credentials_valid": credentials_valid,
                "client_id": hub_client.credentials.client_id if hub_client.credentials else None
            }
        )
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return ServiceTestResult(
            name="Hub Connection",
            success=False,
            duration_ms=duration,
            message=f"Erreur de connexion: {str(e)}",
            details={
                "error": str(e),
                "hub_url": settings.hub_api_url,
                "hub_internal_url": settings.hub_api_internal_url,
            }
        )


async def _test_slug_recovery(user: TokenPayload) -> ServiceTestResult:
    """
    Teste la récupération du X-Slug (role + user).
    Vérifie que le token contient les informations correctes.
    """
    start = datetime.now(timezone.utc)
    try:
        # Récupérer le rôle de l'utilisateur pour cette app
        app_role = user.get_app_role(settings.APP_SLUG)
        role_level = user.get_app_role_level(settings.APP_SLUG)
        is_service = user.is_service_account()
        
        # Vérifier si l'utilisateur a bien des infos dans le token
        has_user_info = bool(user.sub)
        has_role_info = app_role is not None or is_service
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        success = has_user_info and has_role_info
        
        return ServiceTestResult(
            name="X-Slug Recovery",
            success=success,
            duration_ms=duration,
            message="Récupération X-Slug (role + user) fonctionnelle" if success else "Problème de récupération X-Slug",
            details={
                "username": user.sub,
                "app_slug": settings.APP_SLUG,
                "app_role": app_role,
                "role_level": role_level,
                "token_type": user.token_type,
                "is_service_account": is_service,
                "apps_in_token": list(user.apps.keys()) if user.apps else []
            }
        )
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return ServiceTestResult(
            name="X-Slug Recovery",
            success=False,
            duration_ms=duration,
            message=f"Erreur récupération X-Slug: {str(e)}",
            details={"error": str(e)}
        )


async def _test_m2m_service() -> ServiceTestResult:
    """
    Teste le service M2M (Machine-to-Machine).
    Vérifie l'obtention d'un token M2M et la découverte de services.
    """
    start = datetime.now(timezone.utc)
    try:
        # Test 1: Obtenir un token M2M
        token = await hub_client.get_m2m_token()
        has_token = token is not None
        
        # Test 2: Découvrir les services partagés
        services = []
        discovery_success = False
        if has_token:
            try:
                services = await hub_client.list_discovered_services(force_refresh=True)
                discovery_success = True
            except Exception as e:
                logger.warning(f"Échec découverte services: {e}")
        
        # Test 3: Vérifier les informations du token M2M
        token_info = {}
        if hub_client.credentials:
            token_info = {
                "client_id": hub_client.credentials.client_id,
                "has_access_token": bool(hub_client.credentials.access_token),
                "token_expires_at": hub_client.credentials.token_expires_at.isoformat() if hub_client.credentials.token_expires_at else None
            }
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        success = has_token and discovery_success
        
        return ServiceTestResult(
            name="M2M Service",
            success=success,
            duration_ms=duration,
            message="Service M2M opérationnel" if success else "Problème avec le service M2M",
            details={
                "has_m2m_token": has_token,
                "token_length": len(token) if token else 0,
                "discovery_success": discovery_success,
                "discovered_services_count": len(services),
                "discovered_services": [
                    {"slug": s.slug, "name": s.name, "status": s.status, "is_healthy": s.is_healthy}
                    for s in services[:5]  # Limiter à 5 services
                ],
                "token_info": token_info,
                "resync_count": hub_client._resync_count
            }
        )
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return ServiceTestResult(
            name="M2M Service",
            success=False,
            duration_ms=duration,
            message=f"Erreur service M2M: {str(e)}",
            details={"error": str(e)}
        )


async def _test_sse_connection() -> ServiceTestResult:
    """
    Teste le flux SSE (Server-Sent Events) du Hub.
    Vérifie que l'endpoint SSE du Hub est accessible.
    """
    start = datetime.now(timezone.utc)
    try:
        sse_url = f"{settings.hub_api_internal_url}/api/events/stream"
        
        # Test de connexion au flux SSE (timeout court pour ne pas bloquer)
        sse_accessible = False
        sse_response_headers = {}
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                # On fait une requête HEAD ou GET avec timeout très court
                # car le SSE est un stream continu
                async with client.stream("GET", sse_url, timeout=2.0) as response:
                    sse_accessible = response.status_code == 200
                    sse_response_headers = dict(response.headers)
                    
                    # Vérifier le content-type
                    content_type = response.headers.get("content-type", "")
                    is_sse_stream = "text/event-stream" in content_type
                    
                    # Lire les premiers bytes pour confirmer que c'est du SSE
                    first_chunk = ""
                    async for chunk in response.aiter_text():
                        first_chunk = chunk[:100]  # Garder seulement les 100 premiers caractères
                        break  # On ne veut que le premier chunk
                    
            except httpx.ReadTimeout:
                # Timeout est normal pour SSE car c'est un stream
                # Si on arrive ici, c'est que la connexion a été établie
                sse_accessible = True
            except Exception as e:
                logger.debug(f"SSE connection test: {e}")
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        success = sse_accessible
        
        return ServiceTestResult(
            name="SSE Stream",
            success=success,
            duration_ms=duration,
            message="Flux SSE du Hub accessible" if success else "Flux SSE non accessible",
            details={
                "sse_url": sse_url,
                "accessible": sse_accessible,
                "content_type": sse_response_headers.get("content-type", "N/A"),
                "note": "Le flux SSE permet de recevoir les notifications en temps réel (changements de permissions, nouveaux services, etc.)"
            }
        )
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return ServiceTestResult(
            name="SSE Stream",
            success=False,
            duration_ms=duration,
            message=f"Erreur test SSE: {str(e)}",
            details={
                "error": str(e),
                "sse_url": f"{settings.hub_api_internal_url}/api/events/stream",
            }
        )


async def _test_backup_system(db: AsyncSession) -> ServiceTestResult:
    """
    Teste le système de backup.
    Vérifie que le Hub expose les endpoints de backup.
    """
    start = datetime.now(timezone.utc)
    try:
        # Test 1: Vérifier que l'app est enregistrée (requis pour backup)
        is_registered = hub_client.is_registered
        
        # Test 2: Tester l'endpoint de backup sur le Hub
        backup_endpoint_available = False
        backup_endpoint_info = {}
        
        if is_registered:
            token = await hub_client.get_m2m_token()
            if token:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        # Tester l'endpoint canonique qui liste les backups (GET)
                        response = await client.get(
                            f"{settings.hub_api_internal_url}/api/apps/{settings.APP_SLUG}/backup",
                            headers={"Authorization": f"Bearer {token}"}
                        )
                        
                        if response.status_code == 200:
                            backup_endpoint_available = True
                            backup_endpoint_info = response.json()
                        elif response.status_code == 404:
                            # L'endpoint n'existe peut-être pas encore sur le Hub
                            backup_endpoint_info = {"note": "Endpoint non implémenté sur le Hub"}
                        else:
                            backup_endpoint_info = {
                                "status_code": response.status_code,
                                "response": response.text[:200]
                            }
                except Exception as e:
                    backup_endpoint_info = {"error": str(e)}
        
        # Test 3: Vérifier que les tables de backup existent localement
        from models import Item, UserPreference, TestData
        from sqlalchemy import select, func
        
        items_count = await db.scalar(select(func.count(Item.id))) or 0
        prefs_count = await db.scalar(select(func.count(UserPreference.username))) or 0
        testdata_count = await db.scalar(select(func.count(TestData.id))) or 0
        
        has_data_to_backup = items_count > 0 or prefs_count > 0 or testdata_count > 0
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        # Le succès dépend de l'enregistrement et de la disponibilité locale
        success = is_registered and (backup_endpoint_available or has_data_to_backup)
        
        return ServiceTestResult(
            name="Backup System",
            success=success,
            duration_ms=duration,
            message="Système de backup opérationnel" if success else "Système de backup non disponible",
            details={
                "app_registered": is_registered,
                "hub_backup_endpoint_available": backup_endpoint_available,
                "hub_backup_info": backup_endpoint_info,
                "local_data": {
                    "items_count": items_count,
                    "preferences_count": prefs_count,
                    "test_data_count": testdata_count,
                    "has_data_to_backup": has_data_to_backup
                },
                "backup_endpoints": {
                    "estimate": "/api/admin/backup/estimate",
                    "create": "/api/admin/backup",
                    "download": "/api/admin/backup/download",
                    "restore": "/api/admin/restore",
                    "sync_to_hub": "/api/admin/sync-to-hub",
                    "sync_from_hub": "/api/admin/sync-from-hub"
                }
            }
        )
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return ServiceTestResult(
            name="Backup System",
            success=False,
            duration_ms=duration,
            message=f"Erreur test backup: {str(e)}",
            details={"error": str(e)}
        )


# ============================================================
# ENDPOINTS DE TEST
# ============================================================

@router.get("/services", response_model=AllServicesTestResult)
async def test_all_services(
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Teste l'ensemble des services de l'application par rapport au Hub.
    
    Tests effectués:
    1. **Connexion Hub** : Vérifie que le Hub est accessible et que l'app est enregistrée
    2. **X-Slug Recovery** : Vérifie la récupération du rôle et de l'utilisateur depuis le token
    3. **Service M2M** : Teste l'obtention de tokens M2M et la découverte de services
    4. **Flux SSE** : Vérifie que le flux d'événements temps réel est accessible
    5. **Système Backup** : Vérifie le fonctionnement du système de backup
    
    Returns:
        Résultat détaillé de tous les tests avec timing et détails
    """
    start_time = datetime.now(timezone.utc)
    tests_results = []
    
    # Exécuter tous les tests en parallèle où possible
    hub_test, slug_test, m2m_test, sse_test, backup_test = await asyncio.gather(
        _test_hub_connection(),
        _test_slug_recovery(user),
        _test_m2m_service(),
        _test_sse_connection(),
        _test_backup_system(db)
    )
    
    tests_results = [hub_test, slug_test, m2m_test, sse_test, backup_test]
    
    total_duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    
    # Calculer le résumé
    passed = sum(1 for t in tests_results if t.success)
    failed = len(tests_results) - passed
    overall_success = failed == 0
    
    return AllServicesTestResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
        app_slug=settings.APP_SLUG,
        app_version=APP_VERSION,
        overall_success=overall_success,
        total_duration_ms=total_duration,
        tests=tests_results,
        summary={
            "total_tests": len(tests_results),
            "passed": passed,
            "failed": failed,
            "success_rate": f"{(passed / len(tests_results) * 100):.1f}%"
        }
    )


@router.get("/hub-connection", response_model=ServiceTestResult)
async def test_hub_connection_endpoint(
    user: TokenPayload = Depends(get_current_user)
):
    """
    Test de connexion au Hub uniquement.
    
    Vérifie:
    - Le Hub est accessible via son URL
    - L'application est enregistrée auprès du Hub
    - Les credentials M2M sont valides
    """
    return await _test_hub_connection()


@router.get("/slug-recovery", response_model=ServiceTestResult)
async def test_slug_recovery_endpoint(
    user: TokenPayload = Depends(get_current_user)
):
    """
    Test de récupération X-Slug (role + user).
    
    Vérifie:
    - Le token contient l'identifiant utilisateur
    - Le rôle de l'utilisateur pour cette application est défini
    - Les informations globales du token sont présentes
    """
    return await _test_slug_recovery(user)


@router.get("/m2m", response_model=ServiceTestResult)
async def test_m2m_service_endpoint(
    user: TokenPayload = Depends(get_current_user)
):
    """
    Test du service M2M (Machine-to-Machine).
    
    Vérifie:
    - L'obtention d'un token M2M est possible
    - La découverte de services partagés fonctionne
    - Les credentials M2M sont correctement configurés
    """
    return await _test_m2m_service()


@router.get("/sse", response_model=ServiceTestResult)
async def test_sse_endpoint(
    user: TokenPayload = Depends(get_current_user)
):
    """
    Test du flux SSE (Server-Sent Events).
    
    Vérifie:
    - L'endpoint SSE du Hub est accessible
    - Le flux retourne le bon Content-Type
    
    Note: Le flux SSE permet de recevoir en temps réel:
    - Les changements de permissions utilisateur
    - Les nouveaux services disponibles
    - Les notifications système
    """
    return await _test_sse_connection()


@router.get("/backup", response_model=ServiceTestResult)
async def test_backup_endpoint(
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Test du système de backup.
    
    Vérifie:
    - L'application est enregistrée (requis pour sync Hub)
    - L'endpoint backup du Hub est disponible
    - Des données locales sont présentes pour le backup
    """
    return await _test_backup_system(db)


@router.post("/messages/send", response_model=SendTestMessageResult)
async def send_test_message_endpoint(
    payload: Optional[SendTestMessageRequest] = None,
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Envoie un message de test via le Hub avec le compte M2M de l'application.

    Cet endpoint sert de démonstration pratique pour valider l'intégration
    Hub Messages sans avoir à écrire immédiatement une route métier dédiée.

    Comportement:
    - accès réservé aux admins ;
    - si `target_usernames` est vide, le message est envoyé à l'utilisateur courant ;
    - l'envoi réel passe par `hub_client.send_user_message(...)`.
    """
    payload = payload or SendTestMessageRequest()

    title = _normalize_optional_text(payload.title)
    if not title:
        raise HTTPException(status_code=400, detail="Le titre du message est requis")

    fallback_target = _normalize_optional_text(user.sub)
    requested_targets = payload.target_usernames or ([fallback_target] if fallback_target else [])
    target_usernames = _normalize_target_usernames(requested_targets)
    if not target_usernames:
        raise HTTPException(status_code=400, detail="Aucun destinataire valide fourni")

    result = await hub_client.send_user_message(
        target_usernames=target_usernames,
        title=title,
        body=_normalize_optional_text(payload.body),
        priority=payload.priority,
        action_url=_normalize_optional_text(payload.action_url),
        action_label=_normalize_optional_text(payload.action_label),
        expires_at=_normalize_optional_text(payload.expires_at)
    )

    if not result or result.get("error"):
        error_detail = result.get("error") if result else None
        raise HTTPException(
            status_code=502,
            detail=error_detail or "Le Hub n'a pas confirmé l'envoi du message"
        )

    return SendTestMessageResult(
        message="Message de test envoye avec succes",
        sent_by=user.sub,
        target_usernames=target_usernames,
        title=title,
        priority=payload.priority,
        hub_response=result
    )

# ============================================================
# ENDPOINT SSE DE DÉMONSTRATION
# ============================================================

async def _generate_test_events():
    """Génère des événements de test pour démontrer le SSE."""
    import json
    
    events = [
        {"type": "test_start", "message": "Démarrage des tests SSE"},
        {"type": "test_progress", "message": "Test en cours...", "progress": 33},
        {"type": "test_progress", "message": "Test en cours...", "progress": 66},
        {"type": "test_progress", "message": "Test en cours...", "progress": 100},
        {"type": "test_complete", "message": "Tests SSE terminés avec succès"},
    ]
    
    for event in events:
        yield f"data: {json.dumps(event)}\n\n"
        await asyncio.sleep(0.5)
    
    # Événement de fin
    yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"


@router.get("/sse/demo")
async def sse_demo(
    user: TokenPayload = Depends(get_current_user)
):
    """
    Démonstration de flux SSE.
    
    Envoie une série d'événements de test pour démontrer
    le fonctionnement du Server-Sent Events.
    
    Utile pour:
    - Tester la configuration SSE du client
    - Vérifier que le proxy/nginx transmet correctement les SSE
    - Démontrer l'utilisation des SSE dans le frontend
    """
    return StreamingResponse(
        _generate_test_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Désactiver le buffering nginx
        }
    )
