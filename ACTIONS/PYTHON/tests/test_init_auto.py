# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""Tests pour le mode auto de INITIALISE.py."""
import sys
import pytest
from pathlib import Path

# Ajouter ACTIONS/PYTHON au path pour importer INITIALISE
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from INITIALISE import slugify, detect_host_ip, parse_cli_options, collect_app_info_auto


class TestSlugify:
    def test_simple_name(self):
        assert slugify("Gestion des Factures") == "gestion-des-factures"

    def test_accents_removed(self):
        assert slugify("Éléments à traiter") == "elements-a-traiter"

    def test_leading_trailing_spaces(self):
        assert slugify("  Ça marche !  ") == "ca-marche"

    def test_min_length_enforced(self):
        with pytest.raises(ValueError, match=r"Le slug g[ée]n[ée]r[ée].*invalide"):
            slugify("AB")  # 2 caractères après slugify → trop court

    def test_valid_slug_regex(self):
        import re
        slug = slugify("Mon App")
        assert re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', slug)
        assert len(slug) >= 3

    def test_consecutive_hyphens_reduced(self):
        assert slugify("a   b---c") == "a-b-c"


class TestDetectHostIp:
    def test_returns_string(self):
        ip = detect_host_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    def test_returns_valid_format_or_fallback(self):
        ip = detect_host_ip()
        # soit une IP valide, soit le fallback
        import re
        assert re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip) or ip == "192.0.2.11"


class TestParseCliOptions:
    def test_auto_mode_with_name(self):
        opts = parse_cli_options(["Gestion des Factures"])
        assert opts["app_name"] == "Gestion des Factures"
        assert opts["interactive"] is False
        assert opts["profile_path"] is None

    def test_auto_mode_with_name_and_demo(self):
        opts = parse_cli_options(["Gestion des Factures", "--demo"])
        assert opts["app_name"] == "Gestion des Factures"
        assert "--demo" in opts["args"]

    def test_interactive_flag(self):
        opts = parse_cli_options(["--interactive"])
        assert opts["interactive"] is True
        assert opts["app_name"] is None

    def test_profile_mode(self):
        opts = parse_cli_options(["--profile", "/tmp/fake.json"])
        assert opts["profile_path"] == Path("/tmp/fake.json")
        assert opts["app_name"] is None

    def test_no_args_falls_to_interactive(self):
        opts = parse_cli_options([])
        assert opts["app_name"] is None
        assert opts["interactive"] is False
        assert opts["profile_path"] is None


class TestCollectAppInfoAuto:
    def test_returns_expected_config(self):
        config = collect_app_info_auto("Gestion des Factures", clean_demo=True)
        assert config["APP_SLUG"] == "gestion-des-factures"
        assert config["APP_NAME"] == "Gestion des Factures"
        assert config["APP_DESCRIPTION"] == "Application Gestion des Factures"
        assert config["API_PORT"] == ""
        assert config["FRONTEND_PORT"] == ""
        assert config["HUB_API_PORT"] == "8000"
        assert config["HUB_FRONTEND_PORT"] == "80"
        assert config["CLEAN_DEMO"] is True
        assert config["APP_KIND"] == "tool"

    def test_demo_mode(self):
        config = collect_app_info_auto("Test App", clean_demo=False)
        assert config["CLEAN_DEMO"] is False

    def test_force_slug_overrides_auto(self):
        config = collect_app_info_auto("Gestion des Factures", force_slug="my-custom-slug")
        assert config["APP_SLUG"] == "my-custom-slug"

    def test_force_slug_rescues_invalid_name(self):
        """--force-slug doit fonctionner même si le nom produit un slug invalide (< 3 car)."""
        config = collect_app_info_auto("AB", force_slug="ab-app")
        assert config["APP_SLUG"] == "ab-app"
