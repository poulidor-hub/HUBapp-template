"""Settings doit tolérer les variables Hub vides (hubs legacy sans HUB_*_PORT dans le .env)."""

import pytest
from config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isole le test des variables d'environnement réelles."""
    for var in (
        "HUB_HOST", "HUB_INTERNAL_HOST", "HUB_API_PORT", "HUB_FRONTEND_PORT",
        "API_PORT", "FRONTEND_PORT", "APP_HOST",
    ):
        monkeypatch.delenv(var, raising=False)


class TestEmptyHubPorts:
    def test_empty_hub_api_port_falls_back_to_default(self, monkeypatch):
        """HUB_API_PORT vide (subst docker compose) ne doit pas crasher au boot."""
        monkeypatch.setenv("HUB_API_PORT", "")
        settings = Settings()
        assert settings.HUB_API_PORT == 8000

    def test_empty_hub_frontend_port_falls_back_to_default(self, monkeypatch):
        """HUB_FRONTEND_PORT vide (subst docker compose) ne doit pas crasher au boot."""
        monkeypatch.setenv("HUB_FRONTEND_PORT", "")
        settings = Settings()
        assert settings.HUB_FRONTEND_PORT == 80

    def test_valid_ports_are_kept(self, monkeypatch):
        """Une valeur réelle fournie par le .env reste prioritaire."""
        monkeypatch.setenv("HUB_API_PORT", "9000")
        monkeypatch.setenv("HUB_FRONTEND_PORT", "8080")
        settings = Settings()
        assert settings.HUB_API_PORT == 9000
        assert settings.HUB_FRONTEND_PORT == 8080


class TestHubTransfertSettings:
    """Flags opt-in du module hub_transfert (pattern VPN : désactivé par défaut)."""

    def test_hub_transfert_disabled_by_default(self):
        from config import Settings
        s = Settings(_env_file=None)
        assert s.HUB_TRANSFERT_ENABLED is False
        assert s.HUB_TRANSFERT_SLUG == "exemple-app"

    def test_hub_transfert_env_override(self, monkeypatch):
        from config import Settings
        monkeypatch.setenv("HUB_TRANSFERT_ENABLED", "true")
        monkeypatch.setenv("HUB_TRANSFERT_SLUG", "mon-transfert")
        s = Settings(_env_file=None)
        assert s.HUB_TRANSFERT_ENABLED is True
        assert s.HUB_TRANSFERT_SLUG == "mon-transfert"


class TestHttpsParDefaut:
    """Spec 2026-09-19 : HTTPS activé par défaut (défaut sécurisé)."""

    def test_https_enabled_default_true_sans_env(self, monkeypatch):
        """HTTPS_ENABLED absent de l'environnement → défaut True (spec 2026-09-19)."""
        monkeypatch.delenv("HTTPS_ENABLED", raising=False)
        from config import Settings
        s = Settings(_env_file=None)
        assert s.HTTPS_ENABLED is True
