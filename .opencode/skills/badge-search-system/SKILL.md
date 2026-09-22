---
name: badge-search-system
description: 'Install the badge-based global search system on a list page. The search scans ALL fields (including related items), shows clickable badges indicating which fields matched, and supports per-field exclusion. Replaces per-column header filters with a single powerful search bar + badge toolbar. Triggers on: "badge search", "global search", "recherche à badges", "champs de recherche", "exclure un champ de recherche".'
argument-hint: 'Page to install badges on, e.g. "Orders page", "Contracts list", "Budgets view"'
---

# Badge Search System

Installer la recherche globale à badges sur une page liste : un champ unique scanne TOUS les champs (y compris les enregistrements liés/enfants), une toolbar de badges indique quels champs ont matché, et chaque badge est cliquable pour exclure les résultats venant de ce champ.

> Pour les opérations par lot (select-all, bulk update/delete) sur la même page, voir le skill `bulk-operations` — les deux sont indépendants mais cohabitent souvent.

## What It Does

- **One search bar** scanne TOUS les champs de l'entité (y compris les records liés/enfants comme items, documents).
- **Badge toolbar** sous la recherche affiche les champs qui ont matché (ex: "Modèle", "N° Commande", "Fournisseur").
- **Click a badge** pour exclure les résultats matchés via ce champ (style barré). Re-click pour réinclure.
- **Exclusion server-side** — la pagination reste correcte, le total s'ajuste.
- **Multi-field matches** : une entité matchée sur "Modèle" ET "Fournisseur" reste visible quand SEUL "Modèle" est exclu — elle est toujours touchée via "Fournisseur".
- **Remplace les filtres par colonne** — toutes les colonnes passent à `filterable: false` ; la recherche se fait via la barre globale.

## Architecture

```
┌─ Frontend ──────────────────────────────────────────────────┐
│  Search input (toolbar de la page)                          │
│  └─ Badge bar ← detectedFields (useMemo)                    │
│     └─ Click → toggle excludedFields (Set) → API call       │
│  Table de la page ← données du serveur (déjà filtrées)      │
│  Pagination ← total du serveur (après exclusion)            │
└─────────────────────────────────────────────────────────────┘
        │ GET /api/orders?search=dell&exclude_fields=supplier
        ▼
┌─ Backend ───────────────────────────────────────────────────┐
│  Route: parse exclude_fields csv → List[str]                │
│  CRUD:                                                       │
│    1. SQL WHERE (all fields + related items via EXISTS)     │
│    2. If exclude_fields + search active:                    │
│       fetch ALL matches → compute match_fields per row      │
│       → filter: keep if any(match_field NOT excluded)       │
│       → repaginate (skip/limit on filtered list)            │
│    3. Return match_fields in response                       │
│  Schema: OrderOut.match_fields: Optional[List[str]]         │
└─────────────────────────────────────────────────────────────┘
```

## Backend — Installation

### 1. Définir les match fields

Dans le module backend du domaine — ex : `backend/routes/<domain>.py`, **à créer dans l'app dérivée** sur le patron de `backend/routes/items.py` — déclarer **chaque champ searchable** :

```python
_DOMAIN_MATCH_FIELDS = [
    ("field1", "column_or_attr_1"),   # (badge_name, attr_python)
    ("field2", "column_or_attr_2"),
]
_DOMAIN_CHILD_MATCH_FIELDS = [        # Pour les records enfants (items, documents)
    ("child_field1", "child_column_1"),
]
```

> **Règle** : le `badge_name` (1er élément) doit matcher exactement la clé dans `FIELD_LABELS` côté frontend. Snake_case, descriptif.

### 2. SQL search clause (tous les champs + EXISTS enfant)

```python
if search:
    search_pattern = f"%{search}%"
    conditions.append(or_(
        Entity.field1.ilike(search_pattern),
        Entity.field2.ilike(search_pattern),
        # ... tous les champs ...
        # Recherche enfant via EXISTS :
        exists().where(
            (ChildEntity.parent_id == Entity.id)
            & or_(ChildEntity.field_a.ilike(search_pattern),
                  ChildEntity.field_b.ilike(search_pattern))
        ),
    ))
```

### 3. exclude_fields logic — L'INVARIANT CRITIQUE

Après la query, avant pagination. **Aucune implémentation complète n'existe dans ce template** : `compute_domain_match_fields_map` / `_build_child_texts_map` sont **à créer dans l'app dérivée**, dans le module du domaine. Le socle fournit seulement le patron de liste paginée (`backend/routes/items.py::list_items`).

```python
if exclude_fields and search:
    all_entities = session.exec(query).all()
    # ... compute match_fields_map pour TOUS les entities ...
    exclude_set = set(exclude_fields)
    filtered = [
        e for e in all_entities
        if not mf_map_all.get(e.id)
        or any(f not in exclude_set for f in mf_map_all[e.id])
    ]
    total = len(filtered)
    entities = filtered[skip:skip + limit]
else:
    # path normal (count query + offset/limit)
```

> **Invariant** : le filtre d'exclusion garde les lignes où `any(f not in exclude_set for f in match_fields[id])`. Les lignes **sans match_fields** (liste vide ou absentes du map) sont **toujours gardées**. Sinon, exclure "Modèle" supprimerait aussi les entités matchées via "Fournisseur".

### 4. Schema + route

```python
# backend/schemas.py
class EntityOut(BaseModel):
    # ... existing fields ...
    match_fields: Optional[List[str]] = None

# backend/routes/<domain>.py — paramètre query
exclude_fields: Optional[str] = Query(None, description="Champs à exclure (csv: field1,field2)")
# Parse CSV → List[str] ; setter entity_out.match_fields = match_fields_map.get(entity.id)
```

## Frontend — Installation

### 1. Constantes + state

```javascript
// Doit matcher les badge_names du backend _DOMAIN_MATCH_FIELDS
const FIELD_LABELS = { field1: 'Label 1', field2: 'Label 2', child_field1: 'Label Enfant 1' };

const [excludedFields, setExcludedFields] = useState(new Set());

// Détecter les champs matchés sur la page courante
const detectedFields = useMemo(() => {
  if (!filters.search) return [];
  const fieldsSet = new Set();
  for (const entity of entities) {        // entities = page courante
    if (entity.match_fields) entity.match_fields.forEach(f => fieldsSet.add(f));
  }
  // Tri par priorité (champs les plus spécifiques d'abord)
  const priority = ['field1', 'child_field1', 'field2'];
  return [...fieldsSet].sort((a, b) =>
    (priority.indexOf(a) === -1 ? 99 : priority.indexOf(a))
    - (priority.indexOf(b) === -1 ? 99 : priority.indexOf(b)));
}, [entities, filters.search]);
```

### 2. Envoyer exclude_fields à l'API

```javascript
const params = {
  limit: rowsPerPage, offset: first,
  ...(filters.search && { search: filters.search }),
  ...(excludedFields.size > 0 && { exclude_fields: [...excludedFields].join(',') }),
};
// Ajouter excludedFields au tableau de dépendances du useEffect de reload
```

### 3. Rendu de la barre de badges

Le template n'a ni composant `TableToolbar` ni page d'exemple avec badges : ce JSX (badge cliquable + style exclu/barré + bouton « Tout réactiver ») est **à créer dans l'app dérivée**, intégré sous l'input de recherche de la page (cf. la structure de page de `frontend/src/components/DataTable.jsx`). Structure :

```jsx
{/* Barre de badges sous l'input de recherche */}
{detectedFields.length > 0 && (
  <div className="flex items-center gap-1.5 flex-wrap">
    <span className="text-[10px] uppercase ...">Trouvé dans :</span>
    {detectedFields.map(field => (
      <button key={field}
        onClick={() => toggleExclude(field)}
        className={isExcluded(field) ? '... line-through ...' : '... bg-indigo-50 ...'}>
        {FIELD_LABELS[field] || field}
      </button>
    ))}
    {excludedFields.size > 0 && (
      <button onClick={() => setExcludedFields(new Set())}>Tout réactiver</button>
    )}
  </div>
)}
```

> **Imports** : `X` de `lucide-react`, `useMemo` de React. Le `excludedFields` se vide dans `handleResetFilters`.

### 4. Retirer les filtres par colonne

- Toutes les colonnes → `filterable: false` (ou retirer la propriété).
- Si la page utilisait `useColumnFilters` / `ColumnFilterInput` → retirer entièrement (imports, state, params, useEffect deps).
- Retirer `column_filters` des params API.

### 5. (Optionnel) Highlight du texte matché

Le template n'a pas de composant `HighlightText` : **à créer dans l'app dérivée** (ex : `frontend/src/components/HighlightText.jsx`) pour surligner le terme cherché dans les cellules dont le champ est dans `match_fields` et non exclu.

## Vérification

1. `cd frontend && npm run build`
2. `python -m py_compile backend/routes/<domain>.py backend/schemas.py`
3. `make build && make up`
4. Tests manuels :
   - Terme matché sur plusieurs champs → plusieurs badges
   - Terme matché sur un champ enfant → badge enfant
   - Click badge pour exclure → résultats à jour, pagination correcte
   - Entité matchée via plusieurs champs reste quand un seul est exclu
   - « Tout réactiver » → tous les badges reviennent
   - Recherche vide → aucun badge

## Implementation References

> **Note** : ce template ne contient **pas** d'implémentation complète du badge-search. Les fichiers ci-dessous servent de patrons de structure ; le pattern complet (match fields, exclusion server-side, barre de badges) est **à créer dans l'app dérivée** en suivant les sections ci-dessus.

| Réf | Chemin (existe dans le template) |
|---|---|
| Patron CRUD paginé backend (WHERE + count + offset/limit, rôles) | `backend/routes/items.py` |
| Route de liste avec filtre simple (query param) | `backend/routes/test_data.py` |
| Schémas Pydantic (`PaginatedResponse`, `ItemResponse`) | `backend/schemas.py` |
| Modèles SQLAlchemy | `backend/models.py` |
| Enregistrement des routers | `backend/main.py` |
| Page liste frontend (filtre + `useApiQuery`/`useApiMutation`) | `frontend/src/components/DataTable.jsx` |
| Hooks API (fetch + mutations optimistes) | `frontend/src/hooks/useApiQuery.js`, `frontend/src/hooks/useApiMutation.js` |

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Exclusion server-side, pas client-side | Le filtrage client casse la pagination server-side (totalRecords devient faux). Le serveur connaît l'ensemble complet. |
| Fetch ALL matches quand exclude_fields est actif | Pour repaginer correctement après le filtrage Python, il faut connaître tous les matches. La count query seule ne peut pas exprimer le « any match_field not excluded ». |
| Rows sans match_fields toujours gardées | Si une ligne a matché la recherche mais aucun champ spécifique identifié, exclure des champs ne doit pas la cacher. |
| `exclude_fields` en query param csv | Plus simple que `?exclude_fields=a&exclude_fields=b` répété, fonctionne bien avec URL sharing. |
| Champs enfant concaténés dans un seul text map | Évite N+1 queries pendant la computation de match_field. Une seule query batch charge tous les enfants. |

## Anti-Patterns

| Pattern | Pourquoi c'est mal | Correction |
|---|---|---|
| Filtrage client-side pour l'exclusion | Mismatch de pagination — `filteredAssets.length + offset` ≠ total réel | Server-side via `exclude_fields` |
| Liste de champs incomplète | Si un champ est dans le WHERE SQL mais pas dans `_MATCH_FIELDS`, le terme match mais aucun badge → UX confuse | Tenir `_MATCH_FIELDS` synchronisé avec la clause WHERE |
| Badge names mismatch | Le `badge_name` Python (`_MATCH_FIELDS[0]`) doit matcher exactement la clé `FIELD_LABELS` frontend | Convention snake_case des deux côtés |
| Oubli de mise à jour de la route | Ajouter `match_fields` au schema mais pas au handler → badges n'apparaissent jamais | Setter dans la route via `match_fields_map` |
| `excludedFields` absent des deps useEffect | La recherche marche mais l'exclusion ne déclenche pas de reload | Ajouter au tableau de dépendances |
