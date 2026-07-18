# Skill: app-dependencies

# Déclarer et instrumenter les dépendances inter-apps

## When to Use

- "Mon app appelle une autre app en M2M"
- "Je veux déclarer mes dépendances"
- "Où appeler `report_sync` ?"
- "Je veux ajouter une synchro vers une nouvelle app"

## Le fichier `depends.yaml`

À la racine de l'app : `APPS/X/depends.yaml` (voyage avec git).

### Syntaxe minimale

```yaml
depends_on:
  - slug: exemple-app-2
    note: "Catalogue articles"
  - slug: exemple-app
```

### Règles

- `slug` obligatoire, pattern `^[a-z0-9-]+$`, slug **prod** (sans `-ws`)
- `note` optionnel (libre)
- Fichier optionnel : une app sans `depends.yaml` = autonome
- Pas d'auto-dépendance (slug != moi-même)

### Tolérance

- YAML cassé → warning, app traitée comme autonome
- Slug cible inconnu dans le parc → warning, dep ignorée

## Instrumenter `report_sync`

`hub_client.report_sync(target_slug)` signale au hub qu'une synchro vient de se faire.
Met à jour `last_sync_at` dans la table hub `app_dependencies`.

### Où l'appeler

**Après** un M2M réussi, jamais avant. Pattern recommandé :

```python
result = await hub_client.call_discovered_service("exemple-app-2", "/api/articles")
if result.get("status_code") == 200:
    await hub_client.report_sync("exemple-app-2")
```

### Règles

- **Best-effort** : `report_sync` ne lève jamais. Ne pas wrapper dans un try/except
  qui masquerait une erreur métier — l'appel est déjà sécurisé en interne.
- **Pas automatique** : le `hub_client` ne sait pas si l'appel métier a réussi. C'est
  au dev de décider quand reporter.
- Si tu n'appelles jamais `report_sync`, `last_sync_at` reste NULL. Ce n'est pas une
  erreur — le dashboard affichera "jamais synchro (non instrumenté)".

## Tester au workshop

1. Crée ton `depends.yaml`
2. Lance `hubctl` → menu APPS → Atelier (en mode DEV)
3. Sélectionne ton app avec `[→]`. Le hubctl propose automatiquement d'emmener les deps.
4. Valide le groupe complet.
5. Vérifie : toutes les apps du groupe sont dans `APP_Workshop/` avec le suffixe `-ws`.

## Anti-patterns

| Erreur | Conséquence |
|---|---|
| Déclarer une dep sans l'appeler en code | `last_sync_at` reste NULL, suggestion atelier emmène l'app pour rien |
| Oublier `report_sync` après un M2M | Pas de visibilité dashboard sur l'activité |
| Cycle A→B→A dans les YAML | `resolve_group` est protégé (visited set) mais le graphe est sale |
| Référencer un slug `-ws` dans `depends.yaml` | Toujours référencer le slug **prod**. Le hub résout les deux. |
| Wrapper `report_sync` dans un try/except métier | Masque les vraies erreurs. Laisse-le best-effort. |

## Quick Reference

| Ressource | Emplacement |
|---|---|
| Fichier deps | `APPS/X/depends.yaml` |
| Lecture disque hubctl | `hubctl_cli/dependencies.py::build_graph()` |
| Endpoint hub push | `POST /api/apps/dependencies` (service account) |
| Endpoint hub sync | `POST /api/apps/sync-report` (service account) |
| Endpoint hub graphe | `GET /api/apps/dependencies` (admin) |
| Table hub | `app_dependencies` |
| Méthode template | `hub_client.report_sync(target_slug)` |
