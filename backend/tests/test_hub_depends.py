"""Tests de la résolution du fichier depends.yaml.

Bug corrigé : DEPENDS_FILE pointait uniquement vers <racine>/depends.yaml,
qui n'existe pas dans l'image Docker (seul backend/ est copié dans /app).
Le fichier doit être cherché dans backend/ (visible en conteneur sous /app)
puis, à défaut, à la racine du projet.
"""
from pathlib import Path

import hub_client


def _write_yaml(path: Path, slug: str) -> None:
    path.write_text(f"depends_on:\n  - slug: {slug}\n    note: test\n")


def test_no_depends_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(hub_client, "DEPENDS_BACKEND_FILE", tmp_path / "absent-backend.yaml")
    monkeypatch.setattr(hub_client, "DEPENDS_ROOT_FILE", tmp_path / "absent-root.yaml")
    assert hub_client.hub_client._load_depends_yaml() == []


def test_backend_depends_file_has_priority(monkeypatch, tmp_path):
    backend_f = tmp_path / "backend-depends.yaml"
    root_f = tmp_path / "root-depends.yaml"
    _write_yaml(backend_f, "svc-backend")
    _write_yaml(root_f, "svc-root")
    monkeypatch.setattr(hub_client, "DEPENDS_BACKEND_FILE", backend_f)
    monkeypatch.setattr(hub_client, "DEPENDS_ROOT_FILE", root_f)
    deps = hub_client.hub_client._load_depends_yaml()
    assert [d["slug"] for d in deps] == ["svc-backend"]


def test_root_depends_file_fallback(monkeypatch, tmp_path):
    root_f = tmp_path / "root-depends.yaml"
    _write_yaml(root_f, "svc-root")
    monkeypatch.setattr(hub_client, "DEPENDS_BACKEND_FILE", tmp_path / "absent-backend.yaml")
    monkeypatch.setattr(hub_client, "DEPENDS_ROOT_FILE", root_f)
    deps = hub_client.hub_client._load_depends_yaml()
    assert [d["slug"] for d in deps] == ["svc-root"]


def test_invalid_yaml_returns_empty(monkeypatch, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("::: pas du yaml {{{")
    monkeypatch.setattr(hub_client, "DEPENDS_BACKEND_FILE", bad)
    monkeypatch.setattr(hub_client, "DEPENDS_ROOT_FILE", tmp_path / "absent-root.yaml")
    assert hub_client.hub_client._load_depends_yaml() == []
