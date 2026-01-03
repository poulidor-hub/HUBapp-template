"""
Routes de documentation et changelog.
Permet aux agents IA et utilisateurs de consulter l'historique des versions.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pathlib import Path
from typing import Optional
import re

router = APIRouter(prefix="/api/docs", tags=["Documentation"])

# Chemins possibles pour le fichier CHANGELOG.md
# - En local: à la racine du projet (../.. depuis routes/)
# - En Docker: copié dans /app/CHANGELOG.md
def get_changelog_path() -> Path:
    """Trouve le fichier CHANGELOG.md selon l'environnement."""
    # Chemin Docker (prioritaire)
    docker_path = Path("/app/CHANGELOG.md")
    if docker_path.exists():
        return docker_path
    
    # Chemin local (développement)
    local_path = Path(__file__).parent.parent.parent / "CHANGELOG.md"
    if local_path.exists():
        return local_path
    
    # Chemin alternatif
    alt_path = Path(__file__).parent.parent / "CHANGELOG.md"
    if alt_path.exists():
        return alt_path
    
    return docker_path  # Retourner le chemin Docker par défaut

CHANGELOG_PATH = get_changelog_path()


def parse_changelog_versions() -> list[dict]:
    """
    Parse le fichier CHANGELOG.md et extrait les versions.
    Retourne une liste de dicts avec version et date.
    """
    if not CHANGELOG_PATH.exists():
        return []
    
    content = CHANGELOG_PATH.read_text(encoding="utf-8")
    
    # Pattern pour extraire les versions: ## [X.Y.Z] - DATE
    pattern = r"## \[(\d+\.\d+\.\d+)\] - (.+?)(?:\n|$)"
    matches = re.findall(pattern, content)
    
    versions = []
    for version, date in matches:
        versions.append({
            "version": version,
            "date": date.strip()
        })
    
    return versions


def extract_version_content(version: str) -> Optional[str]:
    """
    Extrait le contenu du changelog pour une version spécifique.
    """
    if not CHANGELOG_PATH.exists():
        return None
    
    content = CHANGELOG_PATH.read_text(encoding="utf-8")
    
    # Pattern pour trouver le début de la version
    start_pattern = rf"## \[{re.escape(version)}\] - .+?\n"
    start_match = re.search(start_pattern, content)
    
    if not start_match:
        return None
    
    start_pos = start_match.start()
    
    # Trouver la prochaine version ou la fin
    next_version_pattern = r"\n## \[\d+\.\d+\.\d+\] - "
    next_match = re.search(next_version_pattern, content[start_match.end():])
    
    if next_match:
        end_pos = start_match.end() + next_match.start()
    else:
        # Chercher la section "Format du changelog" ou fin du fichier
        format_match = re.search(r"\n---\n\n## Format du changelog", content[start_match.end():])
        if format_match:
            end_pos = start_match.end() + format_match.start()
        else:
            end_pos = len(content)
    
    return content[start_pos:end_pos].strip()


@router.get("/changelog", response_class=PlainTextResponse)
async def get_changelog(
    since: Optional[str] = Query(None, description="Voir les changements depuis cette version"),
    latest: bool = Query(False, description="Voir uniquement la dernière version")
):
    """
    Retourne le changelog complet ou filtré.
    
    - **since**: Retourne les versions depuis cette version (non incluse)
    - **latest**: Retourne uniquement la dernière version
    """
    if not CHANGELOG_PATH.exists():
        raise HTTPException(status_code=404, detail="Changelog non trouvé")
    
    content = CHANGELOG_PATH.read_text(encoding="utf-8")
    
    if latest:
        versions = parse_changelog_versions()
        if versions:
            version_content = extract_version_content(versions[0]["version"])
            if version_content:
                return version_content
    
    if since:
        versions = parse_changelog_versions()
        version_numbers = [v["version"] for v in versions]
        
        if since in version_numbers:
            since_index = version_numbers.index(since)
            # Retourner toutes les versions plus récentes que 'since'
            newer_versions = version_numbers[:since_index]
            
            if not newer_versions:
                return f"Aucun changement depuis la version {since}"
            
            result_parts = [f"# Changements depuis la version {since}\n"]
            for v in newer_versions:
                v_content = extract_version_content(v)
                if v_content:
                    result_parts.append(v_content)
                    result_parts.append("\n---\n")
            
            return "\n".join(result_parts)
    
    return content


@router.get("/changelog/versions")
async def get_changelog_versions():
    """
    Retourne la liste des versions disponibles dans le changelog.
    Utile pour les agents IA pour connaître les versions existantes.
    """
    versions = parse_changelog_versions()
    
    return {
        "total_versions": len(versions),
        "latest_version": versions[0]["version"] if versions else None,
        "versions": versions
    }


@router.get("/changelog/diff")
async def get_changelog_diff(
    from_version: str = Query(..., description="Version de départ"),
    to_version: Optional[str] = Query(None, description="Version d'arrivée (défaut: dernière)")
):
    """
    Compare deux versions et retourne les changements entre elles.
    Utile pour les agents IA pour savoir quoi mettre à jour.
    """
    versions = parse_changelog_versions()
    version_numbers = [v["version"] for v in versions]
    
    if from_version not in version_numbers:
        raise HTTPException(status_code=404, detail=f"Version {from_version} non trouvée")
    
    if to_version and to_version not in version_numbers:
        raise HTTPException(status_code=404, detail=f"Version {to_version} non trouvée")
    
    to_version = to_version or (versions[0]["version"] if versions else None)
    
    from_index = version_numbers.index(from_version)
    to_index = version_numbers.index(to_version)
    
    if from_index <= to_index:
        return {
            "from_version": from_version,
            "to_version": to_version,
            "changes": [],
            "message": "Aucun changement - version cible identique ou antérieure"
        }
    
    # Récupérer les versions entre from et to (exclus from, inclus to)
    versions_between = version_numbers[to_index:from_index]
    
    changes = []
    for v in versions_between:
        content = extract_version_content(v)
        v_info = next((ver for ver in versions if ver["version"] == v), None)
        changes.append({
            "version": v,
            "date": v_info["date"] if v_info else None,
            "content": content
        })
    
    return {
        "from_version": from_version,
        "to_version": to_version,
        "versions_count": len(changes),
        "changes": changes,
        "action_required": len(changes) > 0
    }


@router.get("/changelog/{version}")
async def get_changelog_version(version: str):
    """
    Retourne le détail d'une version spécifique du changelog.
    """
    versions = parse_changelog_versions()
    version_numbers = [v["version"] for v in versions]
    
    if version not in version_numbers:
        raise HTTPException(
            status_code=404, 
            detail=f"Version {version} non trouvée. Versions disponibles: {', '.join(version_numbers)}"
        )
    
    content = extract_version_content(version)
    
    if not content:
        raise HTTPException(status_code=404, detail=f"Contenu de la version {version} non trouvé")
    
    # Trouver la date de la version
    version_info = next((v for v in versions if v["version"] == version), None)
    
    return {
        "version": version,
        "date": version_info["date"] if version_info else None,
        "content": content,
        "is_latest": versions[0]["version"] == version if versions else False
    }
