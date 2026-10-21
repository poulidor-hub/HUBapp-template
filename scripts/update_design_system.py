#!/usr/bin/env python3
"""
Vendor HUBCSS : synchronise frontend/public/design-system/current/ depuis le
checkout HUBCSS du stack — offline, sha256 vérifiés, tout-ou-rien.

Mode « vendor » canonique des apps du parc (spec 2026-10-21-hubcss-vendor) :
les assets sont committés dans l'app, embarqués dans l'image nginx au build,
et la montée de version est un commit reviewable (git diff, la version est
visible dans current/manifest.json).

Layout source (défaut : ../../HUBCSS, surcharge HUBCSS_DIR ou --from DIR) :
  <source>/manifest.json  — {version, generated_at, files:[{path,size,sha256}]}
  <source>/dist/<path>    — fichiers listés au manifest

Sont copiés les assets runtime : tout le manifest SAUF react/ et python/
(bibliothèques optionnelles). Les fichiers inconnus déjà présents dans la
destination sont préservés — les surcharges légitimes vont dans app.css.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
DEST_DIR = APP_DIR / "frontend" / "public" / "design-system" / "current"
RUNTIME_EXCLUDED = ("react", "python")
MANIFEST_NAME = "manifest.json"


def resolve_source(from_dir: str | None) -> Path:
    """Source du vendor : --from > HUBCSS_DIR > premier <parent>/HUBCSS
    porteur d'un manifest.json (couvre app scaffoldée, repo template et
    worktree agent). Exit 1 actionnable si introuvable."""
    if from_dir:
        return Path(from_dir).resolve()
    if os.environ.get("HUBCSS_DIR"):
        return Path(os.environ["HUBCSS_DIR"]).resolve()
    for parent in APP_DIR.parents:
        candidate = parent / "HUBCSS"
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    _fail(
        f"Checkout HUBCSS introuvable au-dessus de {APP_DIR}\n"
        f"   → Renseignez HUBCSS_DIR=<chemin> ou --from <dir>"
    )


def _fail(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    raise SystemExit(1)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_runtime_asset(rel: str) -> bool:
    """True si l'entrée du manifest est un asset runtime (pas une lib optionnelle)."""
    first = rel.replace("\\", "/").split("/")[0]
    return first not in RUNTIME_EXCLUDED


def load_manifest(source: Path) -> dict:
    """Lit et valide <source>/manifest.json — exit 1 actionnable si absent/invalide."""
    mpath = source / MANIFEST_NAME
    if not mpath.is_file():
        _fail(
            f"{MANIFEST_NAME} introuvable dans {source}\n"
            f"   → Vérifiez le checkout HUBCSS du stack, HUBCSS_DIR, ou --from <dir>"
        )
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"{MANIFEST_NAME} illisible dans {source} : {exc}")
    if not isinstance(manifest.get("files"), list):
        _fail(f"{MANIFEST_NAME} invalide : champ 'files' absent ou non liste")
    return manifest


def plan_entries(source: Path, manifest: dict) -> list[tuple[str, str]]:
    """(relpath, sha256 attendu) pour les assets runtime uniquement."""
    entries: list[tuple[str, str]] = []
    for item in manifest["files"]:
        rel = item.get("path") if isinstance(item, dict) else None
        if not isinstance(rel, str) or not rel or not is_runtime_asset(rel):
            continue
        if rel.startswith(("/", "\\")) or "\\" in rel or ".." in rel.split("/"):
            _fail(f"chemin invalide dans le manifest : {rel!r}")
        if not item.get("sha256"):
            _fail(f"entrée sans sha256 dans le manifest : {rel}")
        entries.append((rel, item["sha256"]))
    if not entries:
        _fail("aucun asset runtime dans le manifest (react/python exclus)")
    return entries


def files_up_to_date(dest: Path, entries: list[tuple[str, str]], source: Path) -> bool:
    """True si tous les assets ET le manifest sont déjà conformes en destination."""
    for rel, sha in entries:
        p = dest / rel
        if not p.is_file() or _sha256(p) != sha:
            return False
    dest_manifest = dest / MANIFEST_NAME
    if not dest_manifest.is_file():
        return False
    return dest_manifest.read_bytes() == (source / MANIFEST_NAME).read_bytes()


def sync(source: Path, dest: Path, entries: list[tuple[str, str]]) -> None:
    """Vérifie TOUS les sha256 en source puis copie — tout-ou-rien."""
    dist = source / "dist"
    staged: list[tuple[str, Path]] = []
    for rel, sha in entries:
        p = dist / rel
        if not p.is_file():
            _fail(
                f"asset absent de la source : dist/{rel}\n"
                f"   → Regénérez le dist (npm run pack dans HUBCSS) ou corrigez la source"
            )
        actual = _sha256(p)
        if actual != sha:
            _fail(
                f"sha256 inattendu pour dist/{rel}\n"
                f"   attendu : {sha}\n   obtenu  : {actual}\n"
                f"   → Source corrompue ou manifest périmé : npm run pack dans HUBCSS"
            )
        staged.append((rel, p))
    for rel, p in staged:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / MANIFEST_NAME, dest / MANIFEST_NAME)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synchronise frontend/public/design-system/current depuis HUBCSS (vendor, sha256 vérifiés)"
    )
    parser.add_argument(
        "--from", dest="from_dir", metavar="DIR",
        help="source alternative : dossier contenant manifest.json + dist/",
    )
    args = parser.parse_args(argv)

    source = resolve_source(args.from_dir)
    dest = DEST_DIR

    manifest = load_manifest(source)
    entries = plan_entries(source, manifest)
    version = manifest.get("version", "?")

    if files_up_to_date(dest, entries, source):
        print(f"✅ Design System à jour ({version}) — {dest}")
        return 0

    sync(source, dest, entries)
    print(f"🔄 Design System {version} copié ({len(entries)} fichiers) → {dest}")
    print("ℹ️  Relisez le git diff (version visible dans current/manifest.json) puis committez.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
