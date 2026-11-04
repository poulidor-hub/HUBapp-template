# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""
Tests du vendor HUBCSS : scripts/update_design_system.py.

Contrat (spec 2026-10-21-hubcss-vendor) :
- copie les assets runtime du manifest (tout SAUF react/, python/) vers
  frontend/public/design-system/current/ + manifest.json pour traçabilité ;
- écriture tout-ou-rien : sha256 tous vérifiés avant la première copie ;
- fichiers inconnus de la destination préservés ;
- source : ../../HUBCSS (défaut), HUBCSS_DIR (env), --from <dir> (option).
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

# Local : <repo>/scripts ; conteneur : /app/scripts (COPY scripts/ de l'image api).
_HERE = Path(__file__).resolve()
for _candidate in (_HERE.parents[2] / "scripts", _HERE.parents[1] / "scripts"):
    if (_candidate / "update_design_system.py").is_file():
        sys.path.insert(0, str(_candidate))
        break

import update_design_system as uds  # noqa: E402

# Assets runtime + une lib optionnelle (react/) pour tester l'exclusion.
ASSETS = {
    "global.css": b":root{--hub-x:1}\n",
    "fonts.css": b"/* fonts */\n",
    "bootstrap-icons/bootstrap-icons.css": b".bi-x:before{content:'x'}\n",
    "bootstrap-icons/fonts/bootstrap-icons.woff": b"WOFF\x00bin",
    "bootstrap-icons/fonts/bootstrap-icons.woff2": b"WOFF2\x00bin",
    "icons/lucide.svg": b"<svg><symbol id='x'/></svg>",
    "react/Icon.js": b"export const Icon = () => null\n",
}


def _fake_hubcss(
    tmp_path: Path,
    version: str = "0.3.1-test",
    bad_sha_for: str | None = None,
    drop_from_dist: str | None = None,
) -> Path:
    """Layout racine HUBCSS : manifest.json + dist/<fichiers>."""
    src = tmp_path / "HUBCSS"
    dist = src / "dist"
    entries = []
    for rel, data in ASSETS.items():
        if rel == drop_from_dist:
            continue  # listé au manifest mais absent de dist/
        p = dist / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        if bad_sha_for == rel:
            sha = "0" * 64
        entries.append({"path": rel, "size": len(data), "sha256": sha})
    (src / "manifest.json").write_text(
        json.dumps({"version": version, "generated_at": "1970-01-01T00:00:00Z", "files": entries}),
        encoding="utf-8",
    )
    return src


@pytest.fixture()
def dest(tmp_path, monkeypatch):
    """Redirige la destination réelle du module vers un tmp (jamais le seed)."""
    d = tmp_path / "current"
    monkeypatch.setattr(uds, "DEST_DIR", d)
    return d


# --- 1. Copie complète + manifest, exclusion react/ --------------------------

def test_sync_copies_runtime_assets_and_manifest(tmp_path, dest):
    src = _fake_hubcss(tmp_path)
    manifest = uds.load_manifest(src)
    entries = uds.plan_entries(src, manifest)
    uds.sync(src, dest, entries)

    for rel, data in ASSETS.items():
        target = dest / rel
        if rel.startswith("react/"):
            assert not target.exists(), "react/ ne doit pas être vendored"
        else:
            assert target.is_file(), f"asset manquant : {rel}"
            assert target.read_bytes() == data
    assert (dest / "manifest.json").is_file(), "manifest copié pour traçabilité"
    assert not (dest / "python").exists()


# --- 2. sha256 faux → refus total, destination intacte -----------------------

def test_sync_refuses_on_sha256_mismatch(tmp_path, dest, capsys):
    src = _fake_hubcss(tmp_path, bad_sha_for="global.css")
    dest.mkdir(parents=True)
    (dest / "keep.css").write_bytes(b"sentinel")

    with pytest.raises(SystemExit) as exc:
        uds.main(["--from", str(src)])
    assert exc.value.code == 1
    assert "sha256" in capsys.readouterr().err
    # tout-ou-rien : rien d'écrit
    assert not (dest / "global.css").exists()
    assert not (dest / "manifest.json").exists()
    assert (dest / "keep.css").read_bytes() == b"sentinel"


# --- 3. manifest absent → message actionnable, exit 1 ------------------------

def test_missing_manifest_actionable(tmp_path, dest, capsys):
    src = tmp_path / "vide"
    src.mkdir()

    with pytest.raises(SystemExit) as exc:
        uds.main(["--from", str(src)])
    assert exc.value.code == 1
    assert "manifest.json introuvable" in capsys.readouterr().err


# --- 4. Idempotence : second run = no écriture -------------------------------

def test_idempotent_no_write(tmp_path, dest):
    src = _fake_hubcss(tmp_path)
    assert uds.main(["--from", str(src)]) == 0
    mtimes = {
        p.relative_to(dest): p.stat().st_mtime_ns
        for p in dest.rglob("*") if p.is_file()
    }
    assert uds.files_up_to_date(dest, uds.plan_entries(src, uds.load_manifest(src)), src) is True
    assert uds.main(["--from", str(src)]) == 0
    mtimes_after = {
        p.relative_to(dest): p.stat().st_mtime_ns
        for p in dest.rglob("*") if p.is_file()
    }
    assert mtimes == mtimes_after, "second run ne doit rien réécrire"


# --- 6bis. F1 (revue) : path traversal via manifest hostile refusé -----------

def test_rejects_path_traversal_in_manifest(tmp_path, dest, capsys):
    src = _fake_hubcss(tmp_path)
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    outside = src / "outside.txt"
    outside.write_bytes(b"secret")
    manifest["files"].append({"path": "../outside.txt", "size": 6, "sha256": hashlib.sha256(b"secret").hexdigest()})
    (src / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        uds.main(["--from", str(src)])
    assert exc.value.code == 1
    capsys.readouterr()
    assert not (dest / "outside.txt").exists()
    assert not (dest.parent / "outside.txt").exists()
    assert outside.read_bytes() == b"secret"


# --- 4bis. F2 (revue) : bump de version seule → manifest réécrit -------------

def test_version_bump_rewrites_manifest(tmp_path, dest):
    src = _fake_hubcss(tmp_path, version="0.3.1-test")
    assert uds.main(["--from", str(src)]) == 0
    m1 = (dest / "manifest.json").read_text(encoding="utf-8")

    (src / "manifest.json").write_text(
        (src / "manifest.json").read_text(encoding="utf-8").replace("0.3.1-test", "0.3.2-test"),
        encoding="utf-8",
    )
    assert uds.files_up_to_date(dest, uds.plan_entries(src, uds.load_manifest(src)), src) is False
    assert uds.main(["--from", str(src)]) == 0
    m2 = (dest / "manifest.json").read_text(encoding="utf-8")
    assert "0.3.2-test" in m2 and m2 != m1


# --- 5. Exclusion par préfixe : react/ listé mais absent de dist/ = ignoré ---

def test_excludes_optional_libraries_only(tmp_path, dest):
    src = _fake_hubcss(tmp_path, drop_from_dist="react/Icon.js")
    assert uds.main(["--from", str(src)]) == 0
    assert (dest / "global.css").is_file()
    assert not (dest / "react").exists()


# --- 6. Fichiers inconnus de la destination préservés ------------------------

def test_unknown_dest_files_preserved(tmp_path, dest):
    src = _fake_hubcss(tmp_path)
    dest.mkdir(parents=True)
    (dest / "custom.css").write_bytes(b"/* override app */")

    assert uds.main(["--from", str(src)]) == 0
    assert (dest / "custom.css").read_bytes() == b"/* override app */"


# --- 7. Surcharge HUBCSS_DIR --------------------------------------------------

def test_hubcss_dir_env_override(tmp_path, dest, monkeypatch):
    src = _fake_hubcss(tmp_path)
    monkeypatch.setenv("HUBCSS_DIR", str(src))

    assert uds.main([]) == 0
    assert (dest / "global.css").is_file()


# --- 8. Source par défaut résolue par recherche du stack (worktree inclus) ---

def test_default_source_resolves_stack_root(tmp_path, monkeypatch):
    """APPS/<app> OU worktree profond → remonter les parents jusqu'au
    premier <racine>/HUBCSS porteur d'un manifest.json (bug worktree)."""
    stack = tmp_path / "stack"
    hubcss = stack / "HUBCSS"
    hubcss.mkdir(parents=True)
    (hubcss / "manifest.json").write_text("{}", encoding="utf-8")
    app = stack / "APPS" / "mon-app" / "scripts"
    app.mkdir(parents=True)

    monkeypatch.setattr(uds, "APP_DIR", app.parent)
    assert uds.resolve_source(None) == hubcss
