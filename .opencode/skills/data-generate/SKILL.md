---
name: data-generate
description: Use when a dev or test environment needs data — populating a list to try a feature, writing fixtures, load-testing pagination, building a demo dataset — and especially when the user offers or points at real production data (CSV export, DB dump, real clients, contracts, emails, phone numbers). Enforces the parc rule that real data never enters a dev/test environment without passing through app-exemple-d first. Triggers on: "générer des données", "données de test", "peupler la base", "seed", "jeu de démo", "fixtures", "charge l'export de prod", "use the real data".
argument-hint: 'What data is needed (volume, realism, target environment) — or the real-data source that must be anonymized before use'
---

# Data Generate (données de test — jamais de données réelles)

Ce skill s'applique à **toute app du parc**, quelle qu'elle soit. Il ne dépend pas du
fait que l'app courante soit app-exemple-d : c'est une règle de parc, invariante.

## Règle d'or

> **Jamais de données réelles en dev/test.** Soit les données sont **générées
> synthétiques** (voie A), soit elles dérivent du réel et ont **obligatoirement
> passé par app-exemple-d** — anonymisation vérifiée — avant d'entrer dans un
> environnement de développement ou de test (voie B).

- **Donnée réelle** : tout enregistrement issu de production ou d'un système
  opérationnel — clients, contrats, emails, téléphones, montants, identifiants —
  y compris un extrait « juste pour voir ».
- **Donnée synthétique** : inventée de toutes pièces, plausible, sans lien avec un
  individu ou un dossier réel.
- **Donnée anonymisée** : donnée réelle transformée par app-exemple-d (masquage
  fake/stat par colonne) au point de ne plus être ré-identifiable.

**Violier la règle « juste un peu », « juste en local », « juste pour la démo »,
c'est la violer tout court.**

## Rationalisations — tableau de réfutation

| Excuse | Réalité |
|---|---|
| « C'est juste ma base de dev locale » | Une base de dev finit dans des dumps, des logs, des captures d'écran, des partages. « Locale » n'est pas « privé ». |
| « Les données sont déjà en base, autant travailler avec » | Le fait accompli ne légitime rien. On **stoppe** la feature, on assainit (purge ou voie B), ensuite seulement on code. |
| « C'est pour une démo, c'est temporaire » | « Temporaire » = jamais supprimé. Et une démo projette des données devant des tiers. |
| « Je varie juste les noms/IDs à la main » | Pseudo-anonymisation artisanale : ré-identifiable par recombinaison (CP + date + montant). Interdit — passer par app-exemple-d. |
| « C'est plus rapide avec le vrai fichier » | La chaîne d'anonymisation prend des minutes. Une fuite de données clients coûte des semaines et engage la responsabilité du parc. |
| « Les tests pytest tournent sur SQLite en mémoire » | Vrai, et sans rapport : le problème est la donnée réelle **dans l'environnement**, pas dans les tests. |
| « L'app courante n'est pas app-exemple-d » | La règle est une règle de parc. app-exemple-d est l'outil, pas le périmètre. |

## Red Flags — STOP et reviens à la règle

- Tu t'apprêtes à écrire un script qui lit un export prod pour l'insérer en dev.
- Tu as découvert des données réelles déjà présentes dans la base de dev.
- Les mots « temporaire », « juste pour la démo », « juste en local » arrivent dans
  la conversation.
- Tu prévois de « modifier légèrement » de vraies lignes pour les rendre anonymes.
- Un fichier de données réelles traîne dans `/tmp`, le home, ou pire, le repo.

## Choix de voie

```
Besoin de données ──▶ Le réalisme doit-il dériver du réel ?
                        │
        non ────────────┴──────────── oui
        │                              │
   VOIE A                        VOIE B (obligatoire)
   synthétique                   anonymisation app-exemple-d
   (défaut)                      AVANT tout usage
```

La voie A suffit dans la grande majorité des cas : tester une liste, une
pagination, un CRUD, une démo. Ne passer en voie B que si la **structure
statistique du réel** est réellement nécessaire (perf sur volumes réalistes,
validation d'un algorithme sur des distributions plausibles).

## Voie A — données synthétiques (défaut)

### A.1 Petit volume (≤ ~50 items)

L'agent appelle directement les endpoints CRUD de l'app avec des payloads
plausibles et cohérents entre eux. Frontend : passer par `useApiMutation`
(invalidation incluse) — cf. skill `frontend-crud-page`. Au-delà d'une page de
liste, voir skill `bulk-operations`.

### A.2 Gros volume (> ~50 items)

Ne pas émettre des centaines d'appels API : écrire un **script one-shot** exécuté
dans le container backend, avec un **seed déterministe enregistré** (reproductible).

```python
"""Seed de données de test — à adapter au modèle de l'app. Exécuter dans le
container backend :  python scripts/seed_test_data.py 1000 42"""
import asyncio, random, sys
from datetime import timedelta
from database import async_session_maker
from models import Item          # à adapter

PRENOMS = ["Alice", "Bruno", "Chloé", "David", "Elena"]
VILLES  = ["Rennes", "Nantes", "Lyon", "Lille", "Bordeaux"]
STATUTS = ["draft", "active", "closed"]

async def main(n_rows: int, seed: int) -> None:
    rng = random.Random(seed)                      # déterministe
    async with async_session_maker() as db:
        for i in range(n_rows):
            db.add(Item(
                label=f"{rng.choice(PRENOMS)} {rng.choice(VILLES)} #{i:05d}",
                amount=round(rng.uniform(10, 5000), 2),
                status=rng.choice(STATUTS),
                created_at=__import__("datetime").datetime.utcnow() - timedelta(days=rng.randint(0, 365)),
            ))
        await db.commit()
    print(f"OK: {n_rows} lignes (seed={seed})")

asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 100,
                 int(sys.argv[2]) if len(sys.argv) > 2 else 42))
```

Règles du script : valeurs **plausibles** (formats emails/téléphones/dates
valides — pour les emails, domaines réservés IANA `example.com`/`example.fr` :
aucune boîte réelle ne peut recevoir de mail, et une purge ciblée
`LIKE '%@example.%'` devient possible), cohérence inter-champs (statut ↔ dates),
volume adapté au test visé, **aucune ligne copiée du réel**. Alternative sans code métier : produire un
`data.json` au format backup puis `POST /api/admin/restore` — cf. skill
`backup-restore-ops` (⚠️ `clear_existing=true` est destructif).

**Volume — petit nombre d'abord.** Quel que soit le volume cible (perf, pagination,
démo), exécuter d'abord le même script à petit nombre (ex. `python scripts/seed_test_data.py 5 42`)
pour valider le workflow bout-en-bout (modèle, contraintes, rendu frontend), puis
seulement le relancer au volume cible. Un gros run qui échoue sur une erreur
détectable à n=5 est du temps perdu — et le debug est noyé dans le volume.

## Voie B — réalisme dérivé du réel : app-exemple-d obligatoire

Chaîne exacte (API app-exemple-d, auth JWT Hub utilisateur — owner du workspace ou
admin ; pas de route M2M pour ce pipeline en v1) :

1. **Minimisation** : exporter depuis la source le strict nécessaire (colonnes
   utiles seulement, volume borné).
2. `POST /api/workspaces` `{name}` → workspace dédié (ex: `anonymisation-dev`).
3. `POST /api/workspaces/{workspace_id}/datasets` — multipart, champ `file`
   (**CSV/XLSX/ODS uniquement** — convertir d'abord, ex: JSON → CSV via pandas).
   Types + profil calculés à l'upload.
4. **Masquage** : configurer les règles fake/stat par colonne (MaskConfig, via UI
   ou API) pour **toute colonne identifiante ou ré-identifiante** (noms, emails,
   téléphones, adresses, dates de naissance, montants rares…).
5. `POST /api/jobs` `{workspace_id, kind: "anonymize", params: {dataset_id,
   mask_config_id, seed?}}` — le `seed?` rend le résultat reproductible
   (`result.effective_seed`).
6. Suivre `GET /api/jobs/{id}` jusqu'à `status: "done"`.
7. Récupérer **uniquement le produit anonymisé** : `GET /api/jobs/{id}/download`
   (CSV).
8. Importer **ce fichier** dans l'environnement de dev — jamais l'export source.
9. Vérifier le réalisme si utile : `POST /api/jobs` `kind: "validate"`
   `{dataset_id, target_dataset_id}` → `result.global_score` (0–100).
10. **Détruire l'export source réel** (fichier local et copie sur la source).

**Règle des dérivés** : produire des **agrégats statistiques** du réel (distributions,
fréquences) pour alimenter une génération synthétique est acceptable. Produire des
**« variantes » de vrais dossiers** (noms mutés, montants perturbés) est interdit :
le résultat reste attribuable au dossier source. En cas de doute → voie A.

## Hygiène (obligatoire dans les deux voies)

- **Seed enregistré** dans la conversation/le commit → reproductibilité.
- **Nettoyage** après le test (purge des données générées) sauf env dédiée jetable.
- **Jamais** de données réelles dans git (fixtures comprises), dans `/tmp`, ni
  dans `uploads/` d'une app autre qu'app-exemple-d.
- **Jamais** cibler la base de prod depuis un script — vérifier `DATABASE_URL`
  avant exécution.
- Volumes bornés : app-exemple-d plafonne `generate` à `GENERATE_MAX_ROWS` ; un
  script maison doit annoncer son volume avant de s'exécuter.

## Implementation References

| Référence | Chemin |
|---|---|
| Patron CRUD backend (rôles, pagination) | `backend/routes/items.py` |
| Données de test partagées (backup/restore) | `backend/routes/test_data.py` |
| Hooks API frontend | `frontend/src/hooks/useApiQuery.js`, `useApiMutation.js` |
| Chaîne d'anonymisation (upload/jobs/download) | app app-exemple-d : `backend/routes/datasets.py`, `backend/routes/jobs.py`, `backend/services/masking.py` (`generate_rows`), `backend/seed/referentials/` |
| Format backup/restore | `docs/BACKUP_RESTORE.md` de l'app + skill `backup-restore-ops` |
| Skills liés | `frontend-crud-page`, `bulk-operations`, `backup-restore-ops`, `hub-m2m-communication` |

## Anti-patterns

| Pattern | Pourquoi c'est mal | Correction |
|---|---|---|
| Importer l'export prod dans la base de dev « pour la démo » | Données personnelles réelles hors de leur finalité ; fiable jusqu'à la fuite | Voie B (anonymisation) puis import du produit anonymisé |
| Travailler sur des données réelles déjà en base | Sunk cost : la feature se construit sur une violation | Stop → purge ou anonymisation → reprise |
| Pseudo-anonymisation artisanale (noms changés à la main) | Ré-identification par recombinaison | app-exemple-d avec règles fake/stat par colonne |
| Centaines d'appels API un à un | Lent, brûle le contexte, partiellement échoué sans rollback | Script one-shot seedé (A.2) ou restore backup |
| Script de seed sans seed ou sans volume annoncé | Non reproductible, effet de bord imprévisible | seed + n_rows en arguments, affichés avant exécution |
| Gros volume lancé d'emblée, échoue sur une erreur détectable à n=5 | Temps perdu, debug noyé dans le volume, reprise partielle à trier | Run réduit d'abord (`n=5`), corriger, puis montée au volume cible |
