"""Certificat Hub du template (hub-app.yaml) — cohérence template ↔ INITIALISE.

Le manifeste déclare l'app auprès du catalogue « Apps GitHub » du Hub
(schéma hub.poulidor/v1 — cf. Hub_base 3.94). Repo-only : dans l'image api,
INITIALISE.py et hub-app.yaml ne sont pas copiés (même convention que
test_initialise_clean.py → skip propre en conteneur).
"""
import importlib.util
import re
import shutil
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_HERE = Path(__file__).resolve().parent
ACTIONS_INIT = _HERE.parents[1] / "ACTIONS" / "PYTHON" / "INITIALISE.py"
TEMPLATE_MANIFEST = _HERE.parents[1] / "hub-app.yaml"

if not ACTIONS_INIT.is_file() or not TEMPLATE_MANIFEST.is_file():
    pytest.skip("INITIALISE.py / hub-app.yaml absents de l'image api — test repo-only",
                allow_module_level=True)

SLUG_RE = re.compile(r"^[a-z0-9-]+$")
VALID_TYPES = {"business", "infra", "tool"}

# Type déclaré par le gabarit. INITIALISE (update_backend_tests_identity)
# substitue cette constante en "tool" pour les apps générées en kind=tool —
# garder la chaîne exacte `EXPECTED_TYPE = "business"` intacte.
EXPECTED_TYPE = "business"


def _load_init_module():
    spec = importlib.util.spec_from_file_location("initmod_certif", ACTIONS_INIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _manifest_dict(content: str) -> dict:
    data = yaml.safe_load(content)
    assert isinstance(data, dict), "hub-app.yaml doit être un mapping YAML"
    return data


def _assert_contract(data: dict) -> None:
    """Contrat hub.poulidor/v1 (validation Hub 3.94, champs requis)."""
    assert data["apiVersion"] == "hub.poulidor/v1"
    assert data["kind"] == "HubApp"
    meta = data["metadata"]
    assert isinstance(meta.get("name"), str) and 1 <= len(meta["name"]) <= 100
    assert SLUG_RE.match(meta["slug"]), f"slug invalide : {meta['slug']}"
    spec = data["spec"]
    assert spec["type"] in VALID_TYPES
    assert spec.get("healthCheck", "").startswith("/")


def test_template_manifest_is_valid_and_matches_initialise_defaults():
    """Le hub-app.yaml du template est un certificat valide aux valeurs par défaut."""
    data = _manifest_dict(TEMPLATE_MANIFEST.read_text(encoding="utf-8"))
    _assert_contract(data)
    # Valeurs par défaut = motifs de substitution attendus par INITIALISE.
    assert data["metadata"]["slug"] == "mon-app"
    assert data["metadata"]["name"] == "Mon Application"
    assert data["spec"]["type"] == EXPECTED_TYPE


def _init_module():
    return _load_init_module()


def test_update_hub_app_manifest_substitutes_identity(tmp_path):
    """update_hub_app_manifest remplace name/slug/description dans le certificat."""
    mod = _init_module()
    assert hasattr(mod, "update_hub_app_manifest")
    shutil.copy(TEMPLATE_MANIFEST, tmp_path / "hub-app.yaml")
    config = {
        "APP_NAME": "Application exemple",
        "APP_SLUG": "exemple-app",
        "APP_DESCRIPTION": "Description de l'application d'exemple",
        "APP_KIND": mod.APP_KIND_CLIENT,
    }
    assert mod.update_hub_app_manifest(tmp_path, config) is True
    data = _manifest_dict((tmp_path / "hub-app.yaml").read_text(encoding="utf-8"))
    assert data["metadata"]["name"] == "Application exemple"
    assert data["metadata"]["slug"] == "exemple-app"
    assert data["metadata"]["description"] == "Description de l'application d'exemple"
    assert data["spec"]["type"] == "business"  # client → business (défaut conservé)
    _assert_contract(data)


def test_update_hub_app_manifest_tool_kind_maps_type(tmp_path):
    """APP_KIND=tool → spec.type: tool (mapping Initialiser → certificat)."""
    mod = _init_module()
    shutil.copy(TEMPLATE_MANIFEST, tmp_path / "hub-app.yaml")
    config = {
        "APP_NAME": "Mon Outil",
        "APP_SLUG": "mon-outil",
        "APP_DESCRIPTION": "Un outil interne",
        "APP_KIND": mod.APP_KIND_TOOL,
    }
    assert mod.update_hub_app_manifest(tmp_path, config) is True
    data = _manifest_dict((tmp_path / "hub-app.yaml").read_text(encoding="utf-8"))
    assert data["spec"]["type"] == "tool"
    _assert_contract(data)


def test_initialise_sequence_includes_certificate_step():
    """Le manifeste est traité avant LICENSE et avant l'auto-suppression."""
    src = ACTIONS_INIT.read_text(encoding="utf-8")
    step_certif = src.find("update_hub_app_manifest(root, config)")
    step_license = src.find("create_license_file(root, config)")
    assert step_certif != -1, "étape certificat absente de main()"
    assert step_license != -1
    assert step_certif < step_license, "le certificat doit être traité avant LICENSE.md"
    # Séquence app fine : 12 étapes, plus aucune cible de l'ancienne génération
    # (backend/config.py, Header.jsx, src/config.js — retirés en 2.35.0).
    assert "[12/12]" in src and "/15]" not in src and "/14]" not in src
    for dead in ("update_backend_config", "update_frontend_header",
                 "update_frontend_config_js", "update_test_fixtures"):
        assert dead not in src, f"fonction morte résiduelle : {dead}"
