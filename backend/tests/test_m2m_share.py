"""
Tests du parsing/validation de l'allowlist de partage IA (m2m_share.yaml).

Format : {share: [...]} (spec §3.1). load_share_decl doit être totale :
aucun cas (YAML absent, malformé, entrée invalide) ne lève d'exception —
l'app qui démarre ne crashe jamais sur une allowlist cassée, elle journalise
et continue.
"""
import logging
import textwrap

from m2m_share import load_share_decl


def _write_yaml(tmp_path, content, subdir=None):
    """
    Écrit un m2m_share.yaml au format spec §3.1 ({share: [...]}) — à la racine
    de tmp_path ou dans un sous-dossier. `content` = entrées non indentées.
    """
    target = tmp_path / subdir if subdir else tmp_path
    target.mkdir(parents=True, exist_ok=True)
    entries = textwrap.indent(textwrap.dedent(content), "  ")
    (target / "m2m_share.yaml").write_text(f"share:\n{entries}", encoding="utf-8")


FULL_ENTRY_YAML = """\
    - path: /api/items
      method: GET
      ia:
        description: "Liste paginée des items"
        example: "GET /api/items?page=1"
        name: "Lister les items"
        klass: "read"
    """


class TestLoadShareDecl:
    """load_share_decl lit base_dir/m2m_share.yaml puis base_dir/backend/m2m_share.yaml."""

    def test_absent_yaml_returns_empty_list(self, tmp_path):
        """Aucun m2m_share.yaml (ni racine, ni backend/) → liste vide, sans exception."""
        assert load_share_decl(tmp_path) == []

    def test_full_declaration_yields_exact_entry(self, tmp_path):
        """Une déclaration complète produit 1 entrée avec les champs exacts."""
        _write_yaml(tmp_path, FULL_ENTRY_YAML)
        assert load_share_decl(tmp_path) == [
            {
                "path": "/api/items",
                "method": "GET",
                "ia": {
                    "description": "Liste paginée des items",
                    "example": "GET /api/items?page=1",
                    "name": "Lister les items",
                    "klass": "read",
                },
            }
        ]

    def test_optional_fields_default_to_none(self, tmp_path):
        """name et klass absents → None dans le bloc ia."""
        _write_yaml(tmp_path, """\
            - path: /api/items
              method: GET
              ia:
                description: "Liste des items"
                example: "GET /api/items"
            """)
        entries = load_share_decl(tmp_path)
        assert entries[0]["ia"]["name"] is None
        assert entries[0]["ia"]["klass"] is None

    def test_backend_subdir_is_fallback(self, tmp_path):
        """YAML absent de la racine mais présent dans backend/ → trouvé."""
        _write_yaml(tmp_path, FULL_ENTRY_YAML, subdir="backend")
        assert len(load_share_decl(tmp_path)) == 1

    def test_root_location_wins_over_backend(self, tmp_path):
        """YAML présent aux deux endroits → celui de la racine gagne (premier trouvé)."""
        _write_yaml(tmp_path, """\
            - path: /api/from-root
              method: GET
              ia:
                description: "Déclaration racine"
                example: "GET /api/from-root"
            """)
        _write_yaml(tmp_path, """\
            - path: /api/from-backend
              method: GET
              ia:
                description: "Déclaration backend"
                example: "GET /api/from-backend"
            """, subdir="backend")
        entries = load_share_decl(tmp_path)
        assert [e["path"] for e in entries] == ["/api/from-root"]

    def test_lowercase_method_normalized(self, tmp_path):
        """method: "get" est normalisé en "GET"."""
        _write_yaml(tmp_path, """\
            - path: /api/items
              method: get
              ia:
                description: "Liste des items"
                example: "GET /api/items"
            """)
        assert load_share_decl(tmp_path)[0]["method"] == "GET"


class TestLoadShareDeclInvalidEntries:
    """Les entrées invalides sont ignorées avec un warning, jamais d'exception."""

    def test_missing_description_ignored(self, tmp_path, caplog):
        """ia.description manquante → entrée ignorée, pas d'exception."""
        _write_yaml(tmp_path, """\
            - path: /api/items
              method: GET
              ia:
                example: "GET /api/items"
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []
        assert any("description" in r.message.lower() for r in caplog.records)

    def test_empty_description_or_example_ignored(self, tmp_path, caplog):
        """description ou example vides/blancs → entrée ignorée + warning."""
        _write_yaml(tmp_path, """\
            - path: /api/empty-desc
              method: GET
              ia:
                description: ""
                example: "GET /api/empty-desc"
            - path: /api/blank-example
              method: GET
              ia:
                description: "Ok"
                example: "   "
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []
        assert len(caplog.records) == 2

    def test_invalid_method_ignored_with_warning(self, tmp_path, caplog):
        """method hors {GET,POST,PUT,PATCH,DELETE} → entrée ignorée + warning."""
        _write_yaml(tmp_path, """\
            - path: /api/stream
              method: TRACE
              ia:
                description: "Flux"
                example: "TRACE /api/stream"
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []
        assert any("TRACE" in r.message for r in caplog.records)

    def test_missing_method_ignored(self, tmp_path, caplog):
        """method absente → entrée ignorée + warning."""
        _write_yaml(tmp_path, """\
            - path: /api/items
              ia:
                description: "Liste des items"
                example: "GET /api/items"
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []

    def test_missing_or_empty_path_ignored(self, tmp_path, caplog):
        """path absent ou vide → entrée ignorée + warning."""
        _write_yaml(tmp_path, """\
            - method: GET
              ia:
                description: "Sans path"
                example: "GET /api/x"
            - path: ""
              method: GET
              ia:
                description: "Path vide"
                example: "GET /api/x"
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []
        assert len(caplog.records) == 2

    def test_missing_or_non_dict_ia_ignored(self, tmp_path, caplog):
        """Bloc ia absent ou non-mapping → entrée ignorée + warning."""
        _write_yaml(tmp_path, """\
            - path: /api/no-ia
              method: GET
            - path: /api/bad-ia
              method: GET
              ia: "pas un mapping"
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []
        assert len(caplog.records) == 2

    def test_non_dict_entry_ignored(self, tmp_path, caplog):
        """Entrée qui n'est pas un mapping (scalaire, liste) → ignorée + warning."""
        _write_yaml(tmp_path, """\
            - "juste une chaîne"
            - [1, 2, 3]
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []
        assert len(caplog.records) == 2

    def test_valid_entries_kept_among_invalid(self, tmp_path, caplog):
        """Les entrées valides sont conservées même si d'autres sont invalides."""
        _write_yaml(tmp_path, """\
            - path: /api/bad
              method: HEAD
              ia:
                description: "Mauvaise méthode"
                example: "HEAD /api/bad"
            - path: /api/good
              method: GET
              ia:
                description: "Bonne entrée"
                example: "GET /api/good"
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            entries = load_share_decl(tmp_path)
        assert [e["path"] for e in entries] == ["/api/good"]
        assert len(caplog.records) == 1


class TestLoadShareDeclResilience:
    """Le fichier ne doit jamais faire crasher l'app au démarrage."""

    def test_malformed_yaml_returns_empty_and_logs_error(self, tmp_path, caplog):
        """YAML malformé (erreur safe_load) → [] + logging.error, sans exception."""
        (tmp_path / "m2m_share.yaml").write_text(
            "share: [unclosed: {bracket\n  - broken", encoding="utf-8"
        )
        with caplog.at_level(logging.ERROR, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_missing_share_key_returns_empty(self, tmp_path, caplog):
        """Mapping racine sans clé 'share' → [] + warning (format spec §3.1 non respecté)."""
        (tmp_path / "m2m_share.yaml").write_text(
            "endpoints:\n  - path: /api/items\n", encoding="utf-8"
        )
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []
        assert any("share" in r.message for r in caplog.records)

    def test_non_list_share_returns_empty(self, tmp_path, caplog):
        """Clé 'share' non-liste (scalaire, mapping, null) → [] + warning."""
        (tmp_path / "m2m_share.yaml").write_text(
            "share: pas une liste\n", encoding="utf-8"
        )
        with caplog.at_level(logging.WARNING, logger="m2m_share"):
            assert load_share_decl(tmp_path) == []
        assert any("share" in r.message for r in caplog.records)

    def test_empty_file_returns_empty_list(self, tmp_path):
        """m2m_share.yaml vide → liste vide, sans exception ni bruit."""
        (tmp_path / "m2m_share.yaml").write_text("", encoding="utf-8")
        assert load_share_decl(tmp_path) == []
