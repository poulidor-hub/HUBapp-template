#!/usr/bin/env python3
"""Tests unitaires de allocate_ports.py — fallback localhost (CAS 1).

L'endpoint Hub /api/apps/allocate-ports n'accepte que des IP réseaux Docker
(whitelist anti-abus). Depuis l'hôte via HUB_HOST=<IP LAN>, la source vue par
hub-api est l'IP LAN → 403. Quand l'app est sur le même serveur que le Hub
(APP_HOST vide), le script doit réessayer via localhost (port publié : la
source devient la gateway Docker → accepté) AVANT de déclencher le fallback
legacy d'allocation locale du sous-réseau.
"""
import json
import urllib.error
from unittest.mock import patch

import allocate_ports


class FakeResponse:
    """Réponse urllib minimale (context manager + read)."""

    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


def _urlopen_side_effect(allowed_urls, payload):
    """Retourne un side_effect : 403 pour toute URL hors allowed_urls."""
    def side_effect(req, timeout=None):
        url = req.full_url
        if url not in allowed_urls:
            raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)
        return FakeResponse(payload)
    return side_effect


ALLOC = {
    "api_port": 9006,
    "frontend_port": 4212,
    "frontend_https_port": 4213,
    "subnet": "10.50.7.0/24",
    "host": "10.50.150.167",
    "reused": True,
}


def _write_env(tmp_path, content: str):
    env = tmp_path / ".env"
    env.write_text(content)
    return env


def test_403_via_hub_host_falls_back_to_localhost(tmp_path, monkeypatch, capsys):
    """CAS 1 : HUB_HOST (LAN) → 403, puis localhost → succès, valeurs écrites."""
    env = _write_env(tmp_path, "APP_SLUG=exemple-app\nHUB_HOST=10.50.150.167\nHUB_API_PORT=8000\nAPP_HOST=\n")
    monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
    localhost_url = "http://localhost:8000/api/apps/allocate-ports"
    with patch.object(allocate_ports.urllib.request, "urlopen",
                      side_effect=_urlopen_side_effect({localhost_url}, ALLOC)), \
         patch.object(allocate_ports, "allocate_subnet_locally", return_value=False) as mock_local:
        rc = allocate_ports.main()
    assert rc == 0
    mock_local.assert_not_called()  # succès via localhost : pas de fallback legacy
    text = env.read_text()
    assert "API_PORT=9006" in text
    assert "FRONTEND_PORT=4212" in text
    assert "FRONTEND_HTTPS_PORT=4213" in text
    assert "APP_SUBNET=10.50.7.0/24" in text


def test_hub_host_ok_no_extra_call(tmp_path, monkeypatch):
    """HUB_HOST répond → un seul appel, pas de fallback."""
    env = _write_env(tmp_path, "APP_SLUG=exemple-app\nHUB_HOST=10.50.150.167\nHUB_API_PORT=8000\nAPP_HOST=\n")
    monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
    lan_url = "http://10.50.150.167:8000/api/apps/allocate-ports"
    with patch.object(allocate_ports.urllib.request, "urlopen",
                      side_effect=_urlopen_side_effect({lan_url}, ALLOC)), \
         patch.object(allocate_ports, "allocate_subnet_locally", return_value=False):
        rc = allocate_ports.main()
    assert rc == 0
    assert "API_PORT=9006" in env.read_text()


def test_remote_host_no_localhost_fallback(tmp_path, monkeypatch):
    """CAS 2 (APP_HOST renseigné, app distante) : localhost n'est PAS essayé."""
    env = _write_env(tmp_path, "APP_SLUG=exemple-app\nHUB_HOST=10.0.0.9\nHUB_API_PORT=8000\nAPP_HOST=192.168.1.200\n")
    monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
    with patch.object(allocate_ports.urllib.request, "urlopen",
                      side_effect=_urlopen_side_effect(set(), ALLOC)) as mock_open, \
         patch.object(allocate_ports, "allocate_subnet_locally", return_value=False) as mock_local:
        rc = allocate_ports.main()
    assert rc == 1
    assert mock_open.call_count == 1  # uniquement HUB_HOST, pas de localhost
    mock_local.assert_called_once()  # fallback legacy conservé sur échec final
    assert "API_PORT=9006" not in env.read_text()


def test_skip_when_already_allocated(tmp_path, monkeypatch, capsys):
    """Ports + subnet déjà remplis → pas d'appel HTTP du tout."""
    env = _write_env(tmp_path, "APP_SLUG=exemple-app\nHUB_HOST=10.50.150.167\n"
                                "API_PORT=9006\nFRONTEND_PORT=4212\nAPP_SUBNET=10.50.7.0/24\n")
    monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
    with patch.object(allocate_ports.urllib.request, "urlopen") as mock_open:
        rc = allocate_ports.main()
    assert rc == 0
    assert mock_open.call_count == 0
    assert "pas d'allocation" in capsys.readouterr().out
