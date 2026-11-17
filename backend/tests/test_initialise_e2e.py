"""E2E INITIALISE — filet de régression du scaffolding complet (repo-only).

Valide l'état COMMITTÉ du template : export `git archive HEAD` dans un tmp,
exécution réelle du scaffold, assertions sur le résultat (exit 0, aucune
étape « Fichier non trouvé », certificat/conftest substitués, scripts
d'action générés, self-destruct, démo absente/présente selon le mode).

C'est le filet qui manquait : INITIALISE a pourri silencieusement pendant
18 jours (2.35.0 → 2.37.0) après la restructuration app fine, faute de
couverture E2E — les tests unitaires ne couvraient que des fonctions isolées.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_HERE = Path(__file__).resolve().parent
REPO = _HERE.parents[1]

pytestmark = pytest.mark.skipif(
    not (REPO / "ACTIONS" / "PYTHON" / "INITIALISE.py").is_file()
    or shutil.which("git") is None,
    reason="INITIALISE.py ou git absent de l'image api — test repo-only",
)


def _export_template(tmp: Path) -> None:
    """Exporte l'état committé (HEAD) du template dans tmp."""
    archive = subprocess.run(
        ["git", "archive", "HEAD"], cwd=REPO, check=True,
        capture_output=True, timeout=60,
    )
    subprocess.run(["tar", "-x", "-C", str(tmp)], input=archive.stdout,
                   check=True, timeout=60)


def _scaffold(tmp: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "INITIALISE.py", "exemple-app", "--yes", *extra],
        cwd=tmp,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_scaffold_auto_clean_exit0(tmp_path):
    """Mode auto (clean par défaut) : scaffold complet sans erreur."""
    tmp = tmp_path / "app"
    tmp.mkdir()
    _export_template(tmp)
    r = _scaffold(tmp)
    assert r.returncode == 0, f"scaffold KO:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}"
    assert "Fichier non trouvé" not in r.stdout, "une étape a ciblé un fichier absent"
    assert "avertissements" not in r.stdout
    # Scripts d'action générés + self-destruct effectué
    assert (tmp / "ACTIONS" / "LINUX" / "START.sh").is_file()
    assert not (tmp / "INITIALISE.py").exists()
    # Certificat substitué + identité mode auto (kind=tool)
    data = yaml.safe_load((tmp / "hub-app.yaml").read_text(encoding="utf-8"))
    assert data["metadata"]["slug"] == "exemple-app"
    assert data["metadata"]["name"] == "exemple-app"
    assert data["spec"]["type"] == "tool"
    # Identité backend tests substituée (conftest APP_SLUG)
    conftest = (tmp / "backend" / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'os.environ["APP_SLUG"] = "exemple-app"' in conftest
    # Démo retirée (mode clean) et router sans la route démo
    assert not (tmp / "frontend" / "src" / "components" / "ExampleList.jsx").exists()
    assert not (tmp / "frontend" / "src" / "routes" / "demo").exists()
    router = (tmp / "frontend" / "src" / "router.js").read_text(encoding="utf-8")
    assert "DemoFormRoute" not in router and "demo/form" not in router
    index_jsx = (tmp / "frontend" / "src" / "routes" / "index.jsx").read_text(
        encoding="utf-8"
    )
    assert "ExampleList" not in index_jsx
    # Point d'entrée débarrassé du service de mocks (import statique sinon
    # cassé après suppression de src/mocks — régression C1 du 17/11/2026)
    main_jsx = (tmp / "frontend" / "src" / "main.jsx").read_text(encoding="utf-8")
    assert "startMockService" not in main_jsx
    assert "mocks" not in main_jsx
    assert "bootstrap" not in main_jsx
    # Résidus MSW retirés (worker public + dep package.json)
    assert not (tmp / "frontend" / "public" / "mockServiceWorker.js").exists()
    pkg = json.loads((tmp / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert "msw" not in pkg.get("dependencies", {})
    assert "msw" not in pkg.get("devDependencies", {})
    assert "msw" not in pkg


def test_scaffold_demo_keeps_demo_content(tmp_path):
    """Mode --demo : scaffold OK, contenu de démonstration conservé."""
    tmp = tmp_path / "app"
    tmp.mkdir()
    _export_template(tmp)
    r = _scaffold(tmp, "--demo")
    assert r.returncode == 0, f"scaffold KO:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}"
    assert "Fichier non trouvé" not in r.stdout
    assert (tmp / "frontend" / "src" / "components" / "ExampleList.jsx").exists()
    data = yaml.safe_load((tmp / "hub-app.yaml").read_text(encoding="utf-8"))
    assert data["metadata"]["slug"] == "exemple-app"
