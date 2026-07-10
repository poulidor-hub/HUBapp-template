"""
Routes M2M (Machine-to-Machine) et découverte de services.
Gère les communications inter-services via le Hub.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
import logging

from config import get_settings
from hub_auth import get_current_user, require_role, require_service_account, TokenPayload
from hub_client import hub_client
from m2m_catalog import build_app_catalog
from fastapi import Request
from schemas import (
    ServiceDiscoveryResponse, DiscoveredServiceResponse
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api", tags=["M2M"])


@router.get("/m2m/status")
async def m2m_status(user: TokenPayload = Depends(require_role("admin"))):
    """
    Statut de la connexion M2M avec le Hub.
    Retourne si l'app est enregistrée et peut obtenir des tokens.
    Réservé aux admins (expose des informations sensibles).
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


@router.get("/apps/discover", response_model=ServiceDiscoveryResponse, tags=["Services"])
async def discover_services(
    force_refresh: bool = Query(False, description="Forcer le rafraîchissement du cache"),
    user: TokenPayload = Depends(get_current_user)
):
    """
    Découvre les services partagés (IS_SHARED=true) disponibles via le Hub.
    
    Cet endpoint permet aux utilisateurs authentifiés de voir les services
    disponibles dans l'écosystème. Utile pour construire des intégrations
    ou afficher les services disponibles dans le frontend.
    
    Utilise le endpoint GET /api/apps/discover du Hub qui retourne tous les 
    services en mode IS_SHARED avec leur api_url dynamique.
    
    Les résultats sont mis en cache pendant 60 secondes.
    
    Returns:
        Liste des services découverts avec leurs informations publiques.
    """
    try:
        services = await hub_client.list_discovered_services(force_refresh=force_refresh)
        
        return ServiceDiscoveryResponse(
            count=len(services),
            services=[
                DiscoveredServiceResponse(
                    slug=svc.slug,
                    name=svc.name,
                    description=svc.description,
                    api_url=svc.api_url,
                    frontend_url=svc.frontend_url,
                    version=svc.version,
                    status=svc.status,
                    is_healthy=svc.is_healthy,
                )
                for svc in services
            ],
            cached_at=hub_client._discovered_services_fetched_at.isoformat() if hub_client._discovered_services_fetched_at else None
        )
    except Exception as e:
        logger.error(f"Erreur découverte services: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Impossible de découvrir les services: {str(e)}"
        )


@router.get("/m2m/discover")
async def discover_m2m_services(
    force_refresh: bool = Query(False, description="Forcer le rafraîchissement du cache"),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Découvre les services partagés (IS_SHARED=true) avec toutes les informations M2M.
    
    Version admin qui inclut des informations techniques supplémentaires
    comme les ports, IPs et détails d'enregistrement.
    
    Utilise le endpoint GET /api/apps/discover du Hub qui retourne tous les 
    services en mode IS_SHARED avec leur api_url dynamique.
    
    Les résultats sont mis en cache pendant 60 secondes.
    
    Returns:
        Liste des services découverts avec toutes leurs informations techniques.
    """
    try:
        services = await hub_client.list_discovered_services(force_refresh=force_refresh)
        
        return {
            "count": len(services),
            "services": [
                {
                    "slug": svc.slug,
                    "name": svc.name,
                    "description": svc.description,
                    # Informations réseau
                    "ip": svc.ip,
                    "api_url": svc.api_url,
                    "api_port": svc.api_port,
                    "frontend_url": svc.frontend_url,
                    "frontend_port": svc.frontend_port,
                    # Métadonnées
                    "version": svc.version,
                    "registered_at": svc.registered_at,
                    "last_seen": svc.last_seen,
                    # Statut
                    "status": svc.status,
                    "is_healthy": svc.is_healthy,
                    "is_shared": svc.is_shared,
                }
                for svc in services
            ],
            "cached_at": hub_client._discovered_services_fetched_at.isoformat() if hub_client._discovered_services_fetched_at else None
        }
    except Exception as e:
        logger.error(f"Erreur découverte services: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Impossible de découvrir les services: {str(e)}"
        )


@router.post("/m2m/call/{service_slug}")
async def call_discovered_service(
    service_slug: str,
    endpoint: str = Query(..., description="Endpoint à appeler sur le service (ex: /api/items)"),
    method: str = Query("GET", description="Méthode HTTP (GET, POST, PUT, DELETE)"),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Appelle un service découvert via son slug et le système M2M.
    
    Utilise l'api_url récupérée dynamiquement via GET /api/apps/discover
    et ajoute le header X-Slug pour l'identification.
    
    Args:
        service_slug: Identifiant unique du service cible
        endpoint: Endpoint à appeler sur le service
        method: Méthode HTTP à utiliser
    
    Returns:
        Réponse du service appelé
    """
    # Vérifier que le service existe
    service = await hub_client.get_service_by_slug(service_slug)
    if not service:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service_slug}' non trouvé parmi les services partagés"
        )
    
    # Appeler le service
    try:
        result = await hub_client.call_discovered_service(
            service_slug=service_slug,
            endpoint=endpoint,
            method=method.upper()
        )
        
        if result is None:
            raise HTTPException(
                status_code=502,
                detail=f"Aucune réponse du service '{service_slug}'"
            )
        
        return {
            "success": True,
            "service": {
                "slug": service.slug,
                "api_url": service.api_url
            },
            "endpoint": endpoint,
            "method": method.upper(),
            "response": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur appel service {service_slug}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Erreur lors de l'appel au service '{service_slug}': {str(e)}"
        )


@router.get("/m2m/catalog")
async def m2m_catalog(
    request: Request,
    sa: TokenPayload = Depends(require_service_account()),
):
    """
    Catalogue M2M de cette application (auto-introspection).

    Retourne la liste de tous les endpoints avec leur niveau d'auth, leurs
    schémas de requête/réponse (résolus) et leurs paramètres. Destiné à être
    consommé par le Hub pour l'export global du catalogue M2M du parc.

    Réservé aux Service Accounts (M2M).
    """
    settings = get_settings()
    return build_app_catalog(
        request.app,
        slug=settings.APP_SLUG,
        name=settings.APP_NAME,
        description=getattr(settings, "APP_DESCRIPTION", None),
        version=getattr(settings, "APP_VERSION", None),
    )
