---
name: app-dependencies
description: Use when an app calls another app via M2M and you need to declare the dependency (depends.yaml at app root) or instrument report_sync so the Hub dashboard reflects inter-app activity. Triggers on: "déclarer une dépendance inter-apps", "depends.yaml", "report_sync", "mon app appelle une autre app", "instrumenter une synchro".
argument-hint: 'What dependency operation is needed (write depends.yaml, instrument report_sync after M2M)'
---

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
  - slug: APP_EXEMPLE
    note: "Catalogue articles"
  - slug: APP_EXEMPLE_E
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
result = await hub_client.call_discovered_service("APP_EXEMPLE", "/api/articles")
if result.get("status_code") == 200:
    await hub_client.report_sync("APP_EXEMPLE")
```

### Règles

- **Best-effort** : `report_sync` ne lève jamais. Ne pas wrapper dans un try/except
  qui masquerait une erreur métier — l'appel est déjà sécurisé en interne.
- **Pas automatique** : le `hub_client` ne sait pas si l'appel métier a réussi. C'est
  au dev de décider quand reporter.
- Si tu n'appelles jamais `report_sync`, `last_sync_at` reste NULL. Ce n'est pas une
  erreur — le dashboard affichera "jamais synchro (non instrumenté)".

## Dépendances et atelier

L'atelier (`./hubctl atelier X`, cf. skill `app-workshop-mover`) fait tourner une
sandbox `-ws` **à côté de la prod, qui reste en place**. Les dépendances déclarées
ne bougent pas : les appels M2M de l'app testée continuent de résoudre vers les
instances **prod** des apps cibles (découverte du Hub). Il n'existe pas de mécanisme
de groupe à « emmener » à l'atelier — si la prod d'une dépendance est down, l'app
en atelier échouera simplement sur ses appels M2M.

Pour tester une montée de version d'une dépendance, lancer un atelier séparé pour
cette dépendance.

## Anti-patterns

| Erreur | Conséquence |
|---|---|
| Déclarer une dep sans l'appeler en code | `last_sync_at` reste NULL ; la déclaration ne reflète rien de réel |
| Oublier `report_sync` après un M2M | Pas de visibilité dashboard sur l'activité |
| Cycle A→B→A dans les YAML | Aucune résolution automatique côté hubctl — le graphe du dashboard devient incohérent |
| Référencer un slug `-ws` dans `depends.yaml` | Toujours référencer le slug **prod**. Le hub résout les deux. |
| Wrapper `report_sync` dans un try/except métier | Masque les vraies erreurs. Laisse-le best-effort. |

## Quick Reference

| Ressource | Emplacement |
|---|---|
| Fichier deps | `APPS/X/depends.yaml` |
| Endpoint hub push | `POST /api/apps/dependencies` (service account) |
| Endpoint hub sync | `POST /api/apps/sync-report` (service account) |
| Endpoint hub graphe | `GET /api/apps/dependencies` (admin) |
| Table hub | `app_dependencies` |
| Méthode template | `hub_client.report_sync(target_slug)` |
