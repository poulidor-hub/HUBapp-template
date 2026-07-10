"""
Tests du tagging __auth_level__ sur les closures d'auth.
Permet l'introspection fiable du niveau d'auth de chaque route.
"""
import pytest
from hub_auth import require_role, require_any_role, require_service_account


class TestAuthTagging:
    """Les closures d'auth portent un attribut __auth_level__ lisible par introspection."""

    def test_require_role_tags_auth_level(self):
        checker = require_role("admin")
        assert getattr(checker, "__auth_level__", None) == "admin"
        assert getattr(checker, "__auth_roles__", None) == ("admin",)

    def test_require_role_manager(self):
        checker = require_role("manager")
        assert checker.__auth_level__ == "manager"

    def test_require_service_account_tags_service(self):
        checker = require_service_account()
        assert checker.__auth_level__ == "service"
        assert checker.__auth_roles__ == ("service",)

    def test_require_any_role_tags_highest(self):
        checker = require_any_role("viewer", "admin")
        # admin (niveau 4) > viewer (niveau 1)
        assert checker.__auth_level__ == "admin"
        assert set(checker.__auth_roles__) == {"viewer", "admin"}

    def test_require_any_role_single(self):
        checker = require_any_role("user")
        assert checker.__auth_level__ == "user"
        assert checker.__auth_roles__ == ("user",)
