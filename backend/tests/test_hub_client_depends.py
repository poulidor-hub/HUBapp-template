from pathlib import Path
from unittest.mock import patch

import pytest

from hub_client import HubClient


def test_load_depends_yaml_returns_empty_when_absent(tmp_path):
    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", tmp_path / "nonexistent.yaml"):
        assert client._load_depends_yaml() == []


def test_load_depends_yaml_reads_entries(tmp_path):
    f = tmp_path / "depends.yaml"
    f.write_text(
        "depends_on:\n"
        "  - slug: exemple-app-2\n"
        "    note: Catalogue\n"
        "  - slug: exemple-app\n"
    )
    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", f):
        result = client._load_depends_yaml()
    assert result == [
        {"slug": "exemple-app-2", "note": "Catalogue"},
        {"slug": "exemple-app"},
    ]


def test_load_depends_yaml_returns_empty_when_no_depends_on_key(tmp_path):
    f = tmp_path / "depends.yaml"
    f.write_text("# just a comment\n")
    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", f):
        assert client._load_depends_yaml() == []


def test_load_depends_yaml_returns_empty_on_corrupted_yaml(tmp_path):
    f = tmp_path / "depends.yaml"
    f.write_text("depends_on: [[unclosed")
    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", f):
        assert client._load_depends_yaml() == []
