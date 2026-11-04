# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""Tests du fallback subnet local dans allocate_ports.py (hub legacy hub_exemple).

Le Hub neuf répond à POST /api/apps/allocate-ports (avec subnet) : comportement
inchangé. Le Hub legacy (HUB_EXEMPLE 3.9.x) ne connaît pas cet endpoint ou les
ports sont déjà figés manuellement : APP_SUBNET est alors alloué LOCALEMENT via
scripts/set_app_subnet.py (plage hub_exemple 10.220.0.0/16), sans jamais masquer
l'erreur bloquante sur les ports manquants.
"""
import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import allocate_ports


def make_fake_mod(free="10.220.0.0/24", taken=frozenset()):
    """Module set_app_subnet factique : déterministe, zéro Docker."""
    calls = {"written": None}

    def set_env_var(path, key, value):
        if key == "APP_SUBNET":
            calls["written"] = value
        Path(path).write_text(Path(path).read_text() + f"{key}={value}\n")

    return types.SimpleNamespace(
        collect_taken=lambda p: (set(taken), True),
        find_free_subnet=lambda t, base: free,
        overlaps=lambda cidr, t: False,
        set_env_var=set_env_var,
        calls=calls,
    ), calls


def fail_if_called(*args, **kwargs):
    raise AssertionError("appel réseau effectué alors qu'aucun n'était attendu")


class FakeResp:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def write_env(tmp_path, content=".env"):
    env = tmp_path / ".env"
    env.write_text(content)
    return env


class TestNoop:
    def test_ports_et_subnet_deja_definis(self, tmp_path, monkeypatch):
        env = write_env(tmp_path, "API_PORT=9000\nFRONTEND_PORT=4250\nAPP_SUBNET=10.220.1.0/24\n")
        monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
        monkeypatch.setattr("urllib.request.urlopen", fail_if_called)
        assert allocate_ports.main() == 0
        assert "APP_SUBNET=10.220.1.0/24" in env.read_text()


class TestFallbackPortsFiges:
    def test_ports_definis_subnet_vide_fallback_local(self, tmp_path, monkeypatch):
        env = write_env(tmp_path, "API_PORT=9000\nFRONTEND_PORT=4250\nAPP_SUBNET=\n")
        monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
        monkeypatch.setattr("urllib.request.urlopen", fail_if_called)
        fake, calls = make_fake_mod(free="10.220.3.0/24")
        assert allocate_ports.allocate_subnet_locally(
            env, loader=lambda: fake) is True
        assert calls["written"] == "10.220.3.0/24"

    def test_main_ports_definis_subnet_vide_sort_zero(self, tmp_path, monkeypatch):
        env = write_env(tmp_path, "API_PORT=9000\nFRONTEND_PORT=4250\nAPP_SUBNET=\n")
        monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
        monkeypatch.setattr("urllib.request.urlopen", fail_if_called)
        fake, calls = make_fake_mod()
        monkeypatch.setattr(allocate_ports, "_load_subnet_module", lambda: fake)
        assert allocate_ports.main() == 0
        assert calls["written"] == "10.220.0.0/24"
        assert "APP_SUBNET=10.220.0.0/24" in env.read_text()

    def test_fallback_impossible_sort_un(self, tmp_path, monkeypatch):
        env = write_env(tmp_path, "API_PORT=9000\nFRONTEND_PORT=4250\nAPP_SUBNET=\n")
        monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
        assert allocate_ports.allocate_subnet_locally(
            env, loader=lambda: None) is False
        assert "APP_SUBNET=" not in env.read_text() or \
            env.read_text().strip().endswith("APP_SUBNET=")


class TestHubNeuf:
    def test_reponse_hub_avec_subnet_pas_de_fallback(self, tmp_path, monkeypatch):
        env = write_env(tmp_path, "APP_SLUG=demo\nHUB_HOST=10.0.0.9\n")
        monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=10: FakeResp({"api_port": 9100, "frontend_port": 4260,
                                              "frontend_https_port": 4261,
                                              "subnet": "10.50.7.0/24"}))
        fake, calls = make_fake_mod()
        monkeypatch.setattr(allocate_ports, "allocate_subnet_locally",
                            lambda p, **kw: (_ for _ in ()).throw(
                                AssertionError("fallback appelé malgré subnet Hub")))
        assert allocate_ports.main() == 0
        content = env.read_text()
        assert "API_PORT=9100" in content
        assert "APP_SUBNET=10.50.7.0/24" in content

    def test_reponse_hub_sans_subnet_fallback_local(self, tmp_path, monkeypatch):
        env = write_env(tmp_path, "APP_SLUG=demo\nHUB_HOST=10.0.0.9\n")
        monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=10: FakeResp({"api_port": 9100, "frontend_port": 4260,
                                              "frontend_https_port": 4261}))
        fake, calls = make_fake_mod(free="10.220.5.0/24")
        monkeypatch.setattr(allocate_ports, "_load_subnet_module", lambda: fake)
        assert allocate_ports.main() == 0
        content = env.read_text()
        assert "API_PORT=9100" in content
        assert calls["written"] == "10.220.5.0/24"
        assert "APP_SUBNET=10.220.5.0/24" in content, "fallback subnet non écrit"


class TestHubLegacy:
    def test_hub_404_ports_manquants_fallback_tente_sort_un(self, tmp_path, monkeypatch):
        def boom(req, timeout=10):
            raise Exception("HTTP Error 404: Not Found")

        env = write_env(tmp_path, "APP_SLUG=demo\nHUB_HOST=10.0.0.9\n")
        monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
        monkeypatch.setattr("urllib.request.urlopen", boom)
        called = []
        monkeypatch.setattr(allocate_ports, "allocate_subnet_locally",
                            lambda p, **kw: called.append(str(p)) or True)
        assert allocate_ports.main() == 1, "ports manquants : doit rester bloquant"
        assert len(called) == 1, "fallback subnet non tenté malgré le 404"
        assert "API_PORT" not in env.read_text(), "ports inventés"

    def test_hub_injoignable_fallback_tente_sort_un(self, tmp_path, monkeypatch):
        def refused(req, timeout=10):
            raise ConnectionError("Connection refused")

        env = write_env(tmp_path, "APP_SLUG=demo\nHUB_HOST=10.0.0.9\n")
        monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
        monkeypatch.setattr("urllib.request.urlopen", refused)
        called = []
        monkeypatch.setattr(allocate_ports, "allocate_subnet_locally",
                            lambda p, **kw: called.append(str(p)) or True)
        assert allocate_ports.main() == 1
        assert len(called) == 1

    def test_hub_host_manquant_sort_un(self, tmp_path, monkeypatch):
        env = write_env(tmp_path, "APP_SLUG=demo\nAPI_PORT=\n")
        monkeypatch.setattr(allocate_ports, "ENV_PATH", env)
        monkeypatch.setattr("urllib.request.urlopen", fail_if_called)
        assert allocate_ports.main() == 1


class TestAllocateSubnetLocally:
    def test_renvoie_false_si_aucun_subnet_libre(self, tmp_path):
        env = write_env(tmp_path, "APP_SUBNET=\n")
        fake, _ = make_fake_mod(free=None)
        assert allocate_ports.allocate_subnet_locally(
            env, loader=lambda: fake) is False
        assert "APP_SUBNET=" == env.read_text().strip().splitlines()[-1]

    def test_renvoie_false_si_chargement_absent(self, tmp_path):
        env = write_env(tmp_path, "APP_SUBNET=\n")
        assert allocate_ports.allocate_subnet_locally(
            env, loader=lambda: None) is False
