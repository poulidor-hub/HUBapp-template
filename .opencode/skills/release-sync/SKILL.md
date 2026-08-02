---
name: release-sync
description: 'Use when synchronizing or verifying the VERSION field across repo files (VERSION, package.json, main.py, .env, docs/API.md) via the bump_version.py tool. Covers consistency checks, version bumps, and sync-env. Triggers on: "version sync", "bump version", "version consistency", "vérifier cohérence version", "make sync-env". For the full release gate (deduce patch/minor/major + CHANGELOG + commit + push main), use the release-on-main skill instead.'
argument-hint: 'Requested sync action, for example: check consistency, bump patch, set 2.5.0'
---

# Release Sync

> **Ce skill = mode d'emploi de `bump_version.py` + fichiers synchronisés.** Pour la **procédure de release complète** (déduction patch/minor/major + CHANGELOG technique + commit + push vers `main`), utiliser le skill parc **`release-on-main`** — c'est la gate obligatoire avant tout push main.

## Fichiers synchronisés

`VERSION` est la source de vérité. `scripts/bump_version.py` propage la version vers :

- [VERSION](../../../VERSION)
- [frontend/package.json](../../../frontend/package.json)
- [backend/main.py](../../../backend/main.py)
- [.env.example](../../../.env.example) + [.env](../../../.env) (si présent)
- [docs/API.md](../../../docs/API.md)

> La liste exhaustive et les détails de substitution vivent dans `scripts/bump_version.py` (source canonique). Hooks : `scripts/install-hooks.sh`.

## Commandes

| Action | Commande |
|---|---|
| Vérifier la cohérence (CI-style, exit code ≠ 0 si incohérent) | `python scripts/bump_version.py --check` |
| Synchroniser la version courante (propager VERSION → tous les fichiers) | `python scripts/bump_version.py` |
| Bumper release | `python scripts/bump_version.py patch\|minor\|major` |
| Setter une version explicite | `python scripts/bump_version.py --set X.Y.Z` |
| Resync `.env` après changements de ports/déploiement | `make sync-env` |

## Vérification post-bump

- `python scripts/bump_version.py --check` doit passer (cohérence).
- [CHANGELOG.md](../../../CHANGELOG.md) contient une entrée pour la version cible (sinon release incomplète — voir `release-on-main`).
- Backend : `make test` ou `make test-cov`.
- Frontend (si changements visibles dans le build Vite) : `cd frontend && npm run build`.

## Guardrails

- **Ne pas hand-éditer** plusieurs fichiers versionnés quand `bump_version.py` existe.
- Changelog manquant = release incomplète, même si la synchro a réussi.
- Le frontend built ne pick pas les env changes au runtime ; rebuilder si la release touche la config Vite-visible.
