# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""Garde anti-IP-morte de sync_hub_host.py.

Une IP Hub annoncée mais injoignable (config Hub obsolète, IP de conteneur)
ne doit jamais être écrite dans le .env : on conserve la valeur courante
joignable, sinon l'IP LAN de l'hôte.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = next(
    (p / "ACTIONS" / "PYTHON" / "sync_hub_host.py"
     for p in Path(__file__).resolve().parents
     if (p / "ACTIONS" / "PYTHON" / "sync_hub_host.py").is_file()),
    None,
)


@pytest.fixture()
def sh(tmp_path, monkeypatch):
    """Module sync_hub_host chargé avec ENV_PATH pointant vers un .env temporaire."""
    if SCRIPT is None:
        pytest.skip("ACTIONS/PYTHON/sync_hub_host.py introuvable depuis les tests")
    spec = importlib.util.spec_from_file_location("sync_hub_host", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_hub_host"] = mod
    spec.loader.exec_module(mod)
    env_file = tmp_path / ".env"
    env_file.write_text("HUB_API_PORT=8000\n")
    monkeypatch.setattr(mod, "ENV_PATH", env_file)
    return mod


def _announce(host, instance="inst-1"):
    return {"host": host, "configured": True, "message": "IP configurée",
            "api_port": 8000, "frontend_port": 80, "instance_id": instance}


def test_ip_morte_courante_joignable_conservee(sh, monkeypatch, capsys):
    """IP annoncée morte + .env courant joignable → on garde le courant."""
    env_file = sh.ENV_PATH
    env_file.write_text("HUB_API_PORT=8000\nHUB_HOST=192.0.2.10\n")
    monkeypatch.setattr(sh, "discover_hub_host", lambda *a, **k: _announce("10.42.0.3"))
    monkeypatch.setattr(
        sh, "query_hub_host_full",
        lambda host, port, timeout=1.5: _announce(host) if host == "192.0.2.10" else None)
    assert sh.main(["--quiet"]) == 0
    assert "HUB_HOST=192.0.2.10" in env_file.read_text()
    # Le courant joignable est conservé via le garde « compat hub legacy »
    out = capsys.readouterr().out
    assert "conservé" in out or "injoignable" in out


def test_ip_morte_vide_fallback_ip_lan(sh, monkeypatch, capsys):
    """IP annoncée morte + .env sans HUB_HOST → adoption de l'IP LAN joignable."""
    env_file = sh.ENV_PATH
    monkeypatch.setattr(sh, "discover_hub_host", lambda *a, **k: _announce("10.42.0.3"))
    monkeypatch.setattr(sh, "get_local_ip", lambda: "192.168.1.199")
    monkeypatch.setattr(
        sh, "query_hub_host_full",
        lambda host, port, timeout=1.5: _announce(host) if host == "192.168.1.199" else None)
    assert sh.main(["--quiet"]) == 0
    assert "HUB_HOST=192.168.1.199" in env_file.read_text()


def test_ip_annoncee_joignable_adoption_normale(sh, monkeypatch):
    """IP annoncée joignable → adoption (comportement historique inchangé)."""
    env_file = sh.ENV_PATH
    monkeypatch.setattr(sh, "discover_hub_host", lambda *a, **k: _announce("192.0.2.12"))
    monkeypatch.setattr(
        sh, "query_hub_host_full",
        lambda host, port, timeout=1.5: _announce(host) if host == "192.0.2.12" else None)
    assert sh.main(["--quiet"]) == 0
    assert "HUB_HOST=192.0.2.12" in env_file.read_text()


def test_tout_mort_hub_host_inchange(sh, monkeypatch):
    """Annonce morte + aucun candidat joignable → aucune écriture."""
    env_file = sh.ENV_PATH
    env_file.write_text("HUB_API_PORT=8000\nHUB_HOST=10.50.150.133\n")
    monkeypatch.setattr(sh, "discover_hub_host", lambda *a, **k: _announce("10.42.0.3"))
    monkeypatch.setattr(sh, "get_local_ip", lambda: "192.168.1.199")
    monkeypatch.setattr(sh, "query_hub_host_full", lambda host, port, timeout=1.5: None)
    assert sh.main(["--quiet"]) == 0
    assert "HUB_HOST=10.50.150.133" in env_file.read_text()
