#!/usr/bin/env python3
"""Tests unitaires de sync_hub_host.py — stdlib uniquement (pas de dépendance pytest externe)."""
import json
import socket
from unittest.mock import MagicMock

import sync_hub_host


# --- read_env ---

def test_read_env_parses_pairs(tmp_path):
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=1.2.3.4\nHUB_API_PORT=8000\n")
    result = sync_hub_host.read_env(env)
    assert result == {"HUB_HOST": "1.2.3.4", "HUB_API_PORT": "8000"}


def test_read_env_ignores_comments_and_blank(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# un commentaire\n\nHUB_HOST=1.2.3.4\n  \n")
    result = sync_hub_host.read_env(env)
    assert result == {"HUB_HOST": "1.2.3.4"}


def test_read_env_missing_file_returns_empty(tmp_path):
    result = sync_hub_host.read_env(tmp_path / "absent.env")
    assert result == {}


# --- set_env_var ---

def test_set_env_var_updates_existing_returns_true(tmp_path):
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=old\n")
    changed = sync_hub_host.set_env_var(env, "HUB_HOST", "new")
    assert changed is True
    assert env.read_text() == "HUB_HOST=new\n"


def test_set_env_var_no_change_returns_false(tmp_path):
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=same\n")
    changed = sync_hub_host.set_env_var(env, "HUB_HOST", "same")
    assert changed is False
    assert env.read_text() == "HUB_HOST=same\n"


def test_set_env_var_appends_missing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("API_PORT=8000\n")
    changed = sync_hub_host.set_env_var(env, "HUB_HOST", "1.2.3.4")
    assert changed is True
    content = env.read_text()
    assert "API_PORT=8000" in content
    assert "HUB_HOST=1.2.3.4" in content


# --- get_local_ip ---

def test_get_local_ip_returns_ip(monkeypatch):
    fake_sock = MagicMock()
    fake_sock.getsockname.return_value = ("192.0.2.12", 12345)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake_sock)
    assert sync_hub_host.get_local_ip() == "192.0.2.12"


def test_get_local_ip_excludes_docker_172(monkeypatch):
    fake_sock = MagicMock()
    fake_sock.getsockname.return_value = ("172.17.0.1", 12345)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake_sock)
    assert sync_hub_host.get_local_ip() is None


def test_get_local_ip_none_on_oserror(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(socket, "socket", boom)
    assert sync_hub_host.get_local_ip() is None


# --- query_hub_host ---

def _urlopen_cm(payload: dict):
    """Construit un faux context manager pour urllib.request.urlopen."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = None
    return cm


def test_query_hub_host_returns_host(monkeypatch):
    cm = _urlopen_cm({"host": "1.2.3.4", "configured": True})
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: cm)
    assert sync_hub_host.query_hub_host("1.2.3.4", "8000") == "1.2.3.4"


def test_query_hub_host_none_on_exception(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("connexion refusée")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert sync_hub_host.query_hub_host("1.2.3.4", "8000") is None


def test_query_hub_host_none_on_empty_host(monkeypatch):
    cm = _urlopen_cm({"host": ""})
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: cm)
    assert sync_hub_host.query_hub_host("1.2.3.4", "8000") is None


# --- discover_hub_host ---

def test_discover_returns_first_responding(monkeypatch):
    answers = {"9.9.9.9": None, "localhost": {"host": "1.2.3.4"}, "127.0.0.1": {"host": "1.2.3.4"}}
    def fake_query(host, port, timeout=1.5):
        return answers.get(host)
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full", fake_query)
    result = sync_hub_host.discover_hub_host(["9.9.9.9", "localhost", "127.0.0.1"], "8000")
    assert result == {"host": "1.2.3.4"}


def test_discover_returns_none_all_fail(monkeypatch):
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full", lambda h, p, t=1.5: None)
    assert sync_hub_host.discover_hub_host(["9.9.9.9", "localhost"], "8000") is None


def test_discover_skips_empty_candidates(monkeypatch):
    seen = []
    def fake_query(host, port, timeout=1.5):
        seen.append(host)
        return None
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full", fake_query)
    sync_hub_host.discover_hub_host(["", "  ", "localhost", None], "8000")
    assert seen == ["localhost"]  # les vides/None sont skippés


# --- main ---

def _patch_env(monkeypatch, tmp_path, hub_host="9.9.9.9", hub_api_port="8000"):
    """Pointe sync_hub_host.ENV_PATH vers un .env temporaire."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"HUB_HOST={hub_host}\nHUB_API_PORT={hub_api_port}\n")
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", env_file)
    return env_file


def test_main_quiet_updates_when_changed(monkeypatch, tmp_path, capsys):
    env_file = _patch_env(monkeypatch, tmp_path, hub_host="9.9.9.9")
    monkeypatch.setattr(sync_hub_host, "discover_hub_host", lambda c, p, t=1.5: "1.2.3.4")
    rc = sync_hub_host.main(["--quiet"])
    assert rc == 0
    assert "HUB_HOST=1.2.3.4" in env_file.read_text()
    assert "1.2.3.4" in capsys.readouterr().out


def test_main_quiet_silent_when_same(monkeypatch, tmp_path, capsys):
    env_file = _patch_env(monkeypatch, tmp_path, hub_host="1.2.3.4")
    monkeypatch.setattr(sync_hub_host, "discover_hub_host", lambda c, p, t=1.5: "1.2.3.4")
    rc = sync_hub_host.main(["--quiet"])
    assert rc == 0
    assert capsys.readouterr().out == ""  # silence total
    assert env_file.read_text() == "HUB_HOST=1.2.3.4\nHUB_API_PORT=8000\n"  # inchangé


def test_main_quiet_silent_when_unreachable(monkeypatch, tmp_path, capsys):
    env_file = _patch_env(monkeypatch, tmp_path, hub_host="9.9.9.9")
    monkeypatch.setattr(sync_hub_host, "discover_hub_host", lambda c, p, t=1.5: None)
    rc = sync_hub_host.main(["--quiet"])
    assert rc == 0
    assert capsys.readouterr().out == ""  # silence, garde current
    assert "HUB_HOST=9.9.9.9" in env_file.read_text()  # inchangé


def test_main_hub_host_flag_writes_directly(monkeypatch, tmp_path, capsys):
    env_file = _patch_env(monkeypatch, tmp_path, hub_host="9.9.9.9")
    called = []
    monkeypatch.setattr(sync_hub_host, "discover_hub_host", lambda *a, **k: called.append(1) or "should-not-happen")
    rc = sync_hub_host.main(["--hub-host", "5.5.5.5"])
    assert rc == 0
    assert called == []  # découverte jamais appelée
    assert "HUB_HOST=5.5.5.5" in env_file.read_text()


def test_main_hub_host_empty_rejected(monkeypatch, tmp_path, capsys):
    env_file = _patch_env(monkeypatch, tmp_path, hub_host="9.9.9.9")
    rc = sync_hub_host.main(["--hub-host", ""])
    assert rc == 1
    assert "HUB_HOST=9.9.9.9" in env_file.read_text()  # .env inchangé (rien effacé)
    assert "vide" in capsys.readouterr().out.lower()


def test_main_interactive_prompts_on_failure(monkeypatch, tmp_path, capsys):
    env_file = _patch_env(monkeypatch, tmp_path, hub_host="9.9.9.9")
    monkeypatch.setattr(sync_hub_host, "discover_hub_host", lambda c, p, t=1.5: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "5.6.7.8")
    rc = sync_hub_host.main([])  # mode interactif (pas de --quiet)
    assert rc == 0
    assert "HUB_HOST=5.6.7.8" in env_file.read_text()
    assert "5.6.7.8" in capsys.readouterr().out


def test_main_interactive_eoferror_returns_1(monkeypatch, tmp_path, capsys):
    _patch_env(monkeypatch, tmp_path, hub_host="9.9.9.9")
    monkeypatch.setattr(sync_hub_host, "discover_hub_host", lambda c, p, t=1.5: None)
    def boom(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", boom)
    rc = sync_hub_host.main([])  # mode interactif sans TTY
    assert rc == 1
    assert "TTY" in capsys.readouterr().out


def test_main_builds_candidate_order(monkeypatch, tmp_path):
    """Vérifie l'ordre des candidats : current, localhost, 127.0.0.1, local_ip, host.docker.internal."""
    _patch_env(monkeypatch, tmp_path, hub_host="9.9.9.9")
    monkeypatch.setattr(sync_hub_host, "get_local_ip", lambda: "192.0.2.12")
    seen = []
    def fake_discover(candidates, port, timeout=1.5):
        seen.extend(candidates)
        return None
    monkeypatch.setattr(sync_hub_host, "discover_hub_host", fake_discover)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")  # Entrée = garder current
    sync_hub_host.main([])
    assert seen == ["9.9.9.9", "localhost", "127.0.0.1", "192.0.2.12", "host.docker.internal"]


# --- Garde : pas de .env (ne jamais créer un .env partiel) ---

def test_main_no_env_does_nothing_interactive(monkeypatch, tmp_path, capsys):
    """Sans .env, main() s'abstient (ne crée rien), message informatif, return 0."""
    missing = tmp_path / "absent.env"  # n'existe pas
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", missing)
    rc = sync_hub_host.main([])  # mode interactif
    assert rc == 0
    assert not missing.exists()  # aucun fichier créé
    out = capsys.readouterr().out
    assert ".env" in out  # message informatif mentionne le .env


def test_main_no_env_quiet_silent(monkeypatch, tmp_path, capsys):
    """Sans .env en --quiet, main() sort silencieusement sans rien créer."""
    missing = tmp_path / "absent.env"
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", missing)
    rc = sync_hub_host.main(["--quiet"])
    assert rc == 0
    assert not missing.exists()
    assert capsys.readouterr().out == ""  # silence total


# --- Ports + instance_id (correctif changement de port) ---

def test_sync_writes_instance_id_and_ports_on_first_contact(tmp_path, monkeypatch):
    """Première rencontre : instance mémorisée + ports alignés sur la réponse."""
    env = tmp_path / ".env"
    env.write_text("APP_SLUG=demo\nHUB_HOST=192.0.2.10\nHUB_API_PORT=18000\n")
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", env)
    resp = {"host": "192.0.2.10", "configured": True,
            "api_port": 18000, "frontend_port": 18080, "instance_id": "a" * 32}
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full",
                        lambda host, port, timeout=1.5: resp)
    rc = sync_hub_host.main(["--quiet"])
    assert rc == 0
    text = env.read_text()
    assert f"HUB_INSTANCE_ID={'a' * 32}" in text
    assert "HUB_FRONTEND_PORT=18080" in text


def test_sync_alerts_and_rewrites_ports_on_mismatch_same_instance(tmp_path, monkeypatch, capsys):
    """Ports différents mais même instance : .env corrigé + alerte forte."""
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=192.0.2.10\nHUB_API_PORT=9000\nHUB_FRONTEND_PORT=80\n"
                   f"HUB_INSTANCE_ID={'a' * 32}\n")
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", env)
    resp = {"host": "192.0.2.10", "configured": True,
            "api_port": 18000, "frontend_port": 18080, "instance_id": "a" * 32}
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full",
                        lambda host, port, timeout=1.5: resp)
    rc = sync_hub_host.main([])  # pas --quiet : l'alerte doit sortir
    assert rc == 0
    out = capsys.readouterr().out
    assert "9000" in out and "18000" in out and "recrée" in out.lower()
    assert "HUB_API_PORT=18000" in env.read_text()


def test_sync_fails_loudly_on_instance_mismatch(tmp_path, monkeypatch, capsys):
    """Instance différente de la mémorisée : aucune écriture, exit 1."""
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=192.0.2.10\nHUB_API_PORT=8000\n"
                   f"HUB_INSTANCE_ID={'a' * 32}\n")
    before = env.read_text()
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", env)
    resp = {"host": "192.0.2.10", "configured": True,
            "api_port": 8000, "frontend_port": 80, "instance_id": "b" * 32}
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full",
                        lambda host, port, timeout=1.5: resp)
    rc = sync_hub_host.main(["--quiet"])
    assert rc == 1
    assert env.read_text() == before  # AUCUNE écriture
    out = capsys.readouterr().out
    assert "a" * 32 in out and "b" * 32 in out
    # Le message doit distinguer ancien/nouveau ET documenter la procédure
    # de bascule volontaire (sinon l'opérateur reste bloqué sans piste).
    assert "mémorisé" in out.lower() or "memorise" in out.lower()
    assert "HUB_INSTANCE_ID" in out
    assert "sync-env" in out


def test_sync_warns_on_legacy_hub_without_ports(tmp_path, monkeypatch, capsys):
    """Hub ancien (sans ports/instance dans la réponse) : warning + comportement IP seule."""
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=192.0.2.10\nHUB_API_PORT=8000\n")
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", env)
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full",
                        lambda host, port, timeout=1.5: {"host": "192.0.2.10"})
    rc = sync_hub_host.main([])
    assert rc == 0
    assert "instance" in capsys.readouterr().out.lower() or "ancienne" in capsys.readouterr().out.lower()
    text = env.read_text()
    assert "HUB_INSTANCE_ID" not in text  # rien inventé
    assert "HUB_API_PORT=8000" in text    # rien changé côté ports


def test_sync_preserves_host_propagation(tmp_path, monkeypatch):
    """HUB_HOST continue d'être propagé (hub déménagé : l'ancienne IP ne
    répond plus, seule la nouvelle répond)."""
    env = tmp_path / ".env"
    env.write_text(f"HUB_HOST=192.0.2.10\nHUB_API_PORT=18000\nHUB_INSTANCE_ID={'a' * 32}\n")
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", env)
    resp = {"host": "192.0.2.11", "configured": True,
            "api_port": 18000, "frontend_port": 18080, "instance_id": "a" * 32}
    # Déménagement réel : le Hub ne répond PLUS via l'ancienne IP (192.0.2.10),
    # la découverte passe par localhost et sa réponse annonce la nouvelle.
    def fake_query(host, port, timeout=1.5):
        return resp if host in ("192.0.2.11", "localhost") else None
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full", fake_query)
    rc = sync_hub_host.main(["--quiet"])
    assert rc == 0
    assert "HUB_HOST=192.0.2.11" in env.read_text()


# --- Garde compat hub legacy : ne pas écraser HUB_HOST si le Hub y répond déjà ---

def test_sync_keeps_host_when_current_answers_legacy_announce(tmp_path, monkeypatch, capsys):
    """Hub legacy : l'annonce contient l'IP docker INTERNE du conteneur hub
    (injoignable depuis le réseau dédié de l'app). Le Hub répond via le
    HUB_HOST courant (IP LAN) → HUB_HOST est CONSERVÉ, annonce ignorée."""
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=192.0.2.10\nHUB_API_PORT=18100\n")
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", env)
    before = env.read_text()
    def fake_query(host, port, timeout=1.5):
        # Le Hub répond via l'IP LAN ; sa réponse annonce son IP interne.
        return {"host": "172.26.0.3"} if host == "192.0.2.10" else None
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full", fake_query)
    rc = sync_hub_host.main(["--quiet"])
    assert rc == 0
    assert env.read_text() == before  # HUB_HOST intact
    assert "conservé" in capsys.readouterr().out


def test_sync_interactive_keeps_host_when_current_answers(tmp_path, monkeypatch, capsys):
    """Mode interactif : même garde, message explicite avec l'annonce ignorée."""
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=192.0.2.10\nHUB_API_PORT=18100\n")
    monkeypatch.setattr(sync_hub_host, "ENV_PATH", env)
    def fake_query(host, port, timeout=1.5):
        return {"host": "172.26.0.3"} if host == "192.0.2.10" else None
    monkeypatch.setattr(sync_hub_host, "query_hub_host_full", fake_query)
    rc = sync_hub_host.main([])
    assert rc == 0
    assert "HUB_HOST=192.0.2.10" in env.read_text()
    out = capsys.readouterr().out
    assert "conservé" in out and "172.26.0.3" in out
