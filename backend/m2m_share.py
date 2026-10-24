"""
Allowlist de partage IA (m2m_share.yaml).

Fournit :
- load_share_decl(base_dir) : lit et valide la déclaration des endpoints
  que l'app autorise explicitement à exposer aux IA (consommé par
  build_app_catalog, cf. m2m_catalog).

Le fichier est cherché dans `base_dir/m2m_share.yaml` puis
`base_dir/backend/m2m_share.yaml` (premier trouvé gagne).

Résilience : ce module ne lève jamais d'exception. Une allowlist absente,
malformée ou contenant des entrées invalides ne doit jamais empêcher l'app
de démarrer — on journalise (warning par entrée, error si YAML illisible)
et on conserve les entrées valides.
"""
import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Méthodes HTTP autorisées dans l'allowlist (normalisées en majuscules).
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# Emplacements du YAML, par ordre de priorité.
_YAML_CANDIDATES = ("m2m_share.yaml", "backend/m2m_share.yaml")


def _non_empty_str(value: Any) -> Optional[str]:
    """Retourne la chaîne épurée si value est un str non blanc, sinon None."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_entry(index: int, raw: Any) -> Optional[dict]:
    """
    Valide une entrée de l'allowlist.

    Retourne l'entrée normalisée, ou None si elle est invalide (un warning
    précis est alors journalisé). Ne lève jamais d'exception.
    """
    where = f"m2m_share.yaml entrée #{index + 1}"

    if not isinstance(raw, dict):
        logger.warning("%s : structure incorrecte (mapping attendu, reçu %s), ignorée",
                       where, type(raw).__name__)
        return None

    path = _non_empty_str(raw.get("path"))
    if not path:
        logger.warning("%s : champ 'path' manquant ou vide, ignorée", where)
        return None

    method = _non_empty_str(raw.get("method"))
    if not method:
        logger.warning("%s : champ 'method' manquant ou vide, ignorée", where)
        return None
    method = method.upper()
    if method not in ALLOWED_METHODS:
        logger.warning("%s : méthode %r hors {%s}, ignorée",
                       where, method, ", ".join(sorted(ALLOWED_METHODS)))
        return None

    ia_raw = raw.get("ia")
    if not isinstance(ia_raw, dict):
        logger.warning("%s : bloc 'ia' manquant ou invalide (mapping attendu), ignorée",
                       where)
        return None

    description = _non_empty_str(ia_raw.get("description"))
    if not description:
        logger.warning("%s : bloc 'ia' sans 'description' non vide, ignorée", where)
        return None

    example = _non_empty_str(ia_raw.get("example"))
    if not example:
        logger.warning("%s : bloc 'ia' sans 'example' non vide, ignorée", where)
        return None

    # name et klass sont optionnels : valeur non-string ou vide -> None.
    return {
        "path": path,
        "method": method,
        "ia": {
            "description": description,
            "example": example,
            "name": _non_empty_str(ia_raw.get("name")),
            "klass": _non_empty_str(ia_raw.get("klass")),
        },
    }


def load_share_decl(base_dir: Path) -> list:
    """
    Lit et valide l'allowlist m2m_share.yaml de l'app.

    Le fichier est cherché dans `base_dir/m2m_share.yaml` puis
    `base_dir/backend/m2m_share.yaml` ; le premier trouvé gagne.

    Retourne une liste d'entrées :
      [{"path": str, "method": "GET", "ia": {description, example, name, klass}}]

    Format attendu (spec §3.1) :
      share:
        - path: /api/items
          method: GET
          ia: {...}

    Résilience (jamais d'exception) :
    - fichier absent -> [] ;
    - YAML malformé  -> [] + logging.error ;
    - clé racine 'share' absente ou non-liste -> [] + logging.warning ;
    - entrée invalide -> ignorée + logging.warning, les entrées valides
      sont conservées.
    """
    base_dir = Path(base_dir)

    yaml_path = None
    for candidate in _YAML_CANDIDATES:
        candidate_path = base_dir / candidate
        if candidate_path.is_file():
            yaml_path = candidate_path
            break
    if yaml_path is None:
        return []

    try:
        with yaml_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        logger.error("%s : YAML illisible (%s), allowlist ignorée", yaml_path, exc)
        return []

    if data is None:  # fichier vide
        return []
    if not isinstance(data, dict) or "share" not in data:
        logger.warning("%s : clé racine 'share' manquante "
                       "(format attendu : mapping {share: [...]}), allowlist ignorée",
                       yaml_path)
        return []
    raw_entries = data["share"]
    if not isinstance(raw_entries, list):
        logger.warning("%s : 'share' doit être une liste d'entrées (reçu %s), allowlist ignorée",
                       yaml_path, type(raw_entries).__name__)
        return []

    entries = []
    for index, raw in enumerate(raw_entries):
        entry = _parse_entry(index, raw)
        if entry is not None:
            entries.append(entry)
    return entries
