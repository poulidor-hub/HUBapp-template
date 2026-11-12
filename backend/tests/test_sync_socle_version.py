# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""
Tests sync_socle_version : l'échec « image socle absente » ne doit frapper
que les apps réellement liées au socle — clé APP_SOCLE_VERSION dans .env
OU exigée par un docker-compose*.yml.

Spec 2026-10-21-hubcss-vendor, lot 4 : clé absente → no-op silencieux (exit 0),
quelle que soit la présence de l'image — sinon `make dev/build/up` échoue pour
toute app fraîchement scaffoldée sur une station sans image socle.

Fix 2026-11-12 : les apps héritées migrées vers le compose socle-based exigent
APP_SOCLE_VERSION dans le compose mais leur .env (pré-socle) ne l'a pas — la
détection par la seule clé du .env les faisait passer pour standalone (no-op)
et le build échouait ensuite sur ${APP_SOCLE_VERSION:?}. Le compose est donc
le signal de liaison : compose exige + image construite → clé ajoutée ;
compose exige + image absente → exit 1 actionnable (« hubctl socle build »).
"""
import sys
from pathlib import Path

# Local : <repo>/scripts ; conteneur : /app/scripts (COPY scripts/ de l'image api).
_HERE = Path(__file__).resolve()
for _candidate in (_HERE.parents[2] / "scripts", _HERE.parents[1] / "scripts"):
    if (_candidate / "sync_socle_version.py").is_file():
        sys.path.insert(0, str(_candidate))
        break

import sync_socle_version as svs  # noqa: E402

_COMPOSE_SOCLE = (
    "services:\n"
    "  api:\n"
    "    build:\n"
    "      args:\n"
    "        - SOCLE_VERSION=${APP_SOCLE_VERSION:?APP_SOCLE_VERSION manquant}\n"
)


def _setup(tmp_path, monkeypatch, env_content: str | None, compose_content: str | None = None):
    env = tmp_path / ".env"
    if env_content is not None:
        env.write_text(env_content, encoding="utf-8")
    if compose_content is not None:
        (tmp_path / "docker-compose.yml").write_text(compose_content, encoding="utf-8")
    monkeypatch.setattr(svs, "ENV_PATH", env)
    monkeypatch.setattr(svs, "APP_DIR", tmp_path)
    monkeypatch.setattr(svs, "socle_version", lambda: "2.27.0")
    monkeypatch.setattr(svs, "image_exists", lambda version: False)


def test_no_env_key_no_compose_noop_even_if_image_missing(tmp_path, monkeypatch, capsys):
    """Ni clé .env ni référence compose (app non liée au socle) + image absente → exit 0."""
    _setup(tmp_path, monkeypatch, "APP_SLUG=mon-app\n")
    assert svs.main() == 0
    assert "no-op" in capsys.readouterr().out


def test_env_key_present_still_fails(tmp_path, monkeypatch, capsys):
    """Clé présente (vraie app fine) + image absente → exit 1 actionnable."""
    _setup(tmp_path, monkeypatch, "APP_SOCLE_VERSION=2.26.0\n")
    assert svs.main() == 1
    assert "hubctl socle build" in capsys.readouterr().err


def test_compose_requires_key_legacy_app_gets_added(tmp_path, monkeypatch, capsys):
    """App héritée : compose exige la clé, .env (pré-socle) ne l'a pas, image
    socle construite → clé ajoutée automatiquement, exit 0 (build ensuite OK)."""
    _setup(tmp_path, monkeypatch, "APP_SLUG=mon-app\n", compose_content=_COMPOSE_SOCLE)
    monkeypatch.setattr(svs, "image_exists", lambda version: True)
    assert svs.main() == 0
    out = capsys.readouterr().out
    assert "ajouté au .env" in out
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "APP_SOCLE_VERSION=2.27.0" in env_text


def test_compose_requires_key_legacy_app_image_missing_fails(tmp_path, monkeypatch, capsys):
    """App héritée : compose exige la clé mais image socle absente → exit 1
    actionnable AVANT le message buildkit obscur (offline-first)."""
    _setup(tmp_path, monkeypatch, "APP_SLUG=mon-app\n", compose_content=_COMPOSE_SOCLE)
    assert svs.main() == 1
    assert "hubctl socle build" in capsys.readouterr().err


def test_missing_env_file_noop(tmp_path, monkeypatch):
    """Pas de .env du tout → no-op (aligné sur le lot 4 : clé absente ⇒ no-op ;
    l'ancien code échouait avant ce fix dès que l'image socle était absente)."""
    _setup(tmp_path, monkeypatch, None)
    assert svs.main() == 0
