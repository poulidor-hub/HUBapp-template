---
name: bulk-operations
description: Use when a list page needs batch operations on many rows at once — "select all filtered" across server-side pagination, bulk update (status, assignment, category), or bulk delete. The backend resolves target IDs from active filters so the operation applies to all matching rows, not just the current page. Triggers on: "select all filtered", "bulk update", "bulk delete", "batch operations", "sélectionner tous les filtrés", "action de masse", "modification en lot", "suppression en lot".
argument-hint: 'What bulk operation is needed (select-all across pagination, bulk status change, bulk delete, bulk assign metadata)'
---

# Bulk Operations (Select All Filtered + Batch Update/Delete)

Quand une page liste a de la pagination server-side, l'utilisateur ne peut interagir qu'avec les lignes de la page courante. Ce skill documente comment ajouter **« sélectionner tous les éléments correspondant aux filtres actifs »** et appliquer des opérations par lot (changement de statut, assignation, suppression).

> Coexiste souvent avec le skill `badge-search-system` (recherche à badges) — les deux utilisent la pagination server-side et les filtres, mais sont indépendants.

## Architecture

```
┌─ Frontend ─────────────────────────────────────────────────────┐
│  Checkbox column (admin only)                                   │
│  └─ Page-level selection → "Select all X filtered" link        │
│     └─ selectAllMode: tracks deselectedIds (not selectedIds)   │
│        └─ Batch action bar (status change, delete...)          │
│           └─ POST /orders/bulk-update (filter params or IDs)   │
│              └─ Backend: resolve target IDs from filters       │
│                 └─ Apply UPDATE/DELETE in single SQL stmt      │
└────────────────────────────────────────────────────────────────┘
```

**Invariant clé** : en mode `select_all`, on suit les **désélections** (`deselectedIds`), pas les sélections — parce qu'il y a potentiellement des milliers de lignes filtrées qu'on ne peut pas toutes énumérer.

## Phase 1 — Backend : schémas bulk

Dans `backend/schemas.py` (classes **à créer** pour le domaine, à côté des patrons `ItemResponse` / `PaginatedResponse`) :

```python
class DomainBulkUpdateIn(BaseModel):
    order_ids: Optional[List[int]] = None        # IDs explicites (sélection page courante)
    select_all: bool = False                      # appliquer à tous les filtrés
    exclude_order_ids: Optional[List[int]] = None  # IDs à exclure (désélectionnés après select-all)
    # Filtres (utilisés si select_all=True) — doivent matcher les filtres de la route list
    search: Optional[str] = None
    year: Optional[int] = None
    status: Optional[str] = None
    # Champs à modifier
    set_status: Optional[str] = None
    set_budget_line_id: Optional[int] = None

class DomainBulkDeleteIn(BaseModel):
    order_ids: Optional[List[int]] = None
    select_all: bool = False
    exclude_order_ids: Optional[List[int]] = None
    # ... champs filtres ...

class OrderBulkOperationResult(BaseModel):
    success_count: int = 0
    error_count: int = 0
    errors: List[str] = []
```

## Phase 2 — Backend : helpers CRUD

Dans le module backend du domaine — ex : `backend/routes/<domain>.py` **à créer dans l'app dérivée** sur le patron de `backend/routes/items.py` (ou un `backend/crud.py` extrait si le domaine grandit) — extraire la logique de filtre dans une fonction réutilisable et ajouter :

```python
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

async def list_domain_ids_by_filters(db: AsyncSession, search, year, ...) -> List[int]:
    """Retourne tous les IDs matchant les filtres (sans pagination)."""
    conditions = _build_domain_filter_conditions(...)
    result = await db.execute(select(Domain.id).where(*conditions))
    return result.scalars().all()

async def bulk_update_domains(db: AsyncSession, order_ids=None, select_all=False,
                               exclude_order_ids=None, set_status=None, ...) -> int:
    if order_ids:
        target_ids = order_ids
    elif select_all:
        target_ids = await list_domain_ids_by_filters(db, ...)
    # Retirer les IDs explicitement désélectionnés
    if exclude_order_ids:
        target_ids = [id for id in target_ids if id not in set(exclude_order_ids)]
    if not target_ids:
        return 0
    stmt = update(Domain).where(Domain.id.in_(target_ids)).values(...)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount
```

> **Invariant critique** : `exclude_order_ids` gère les éléments que l'utilisateur a explicitement décochés après « select all ». Le backend doit les filtrer avant l'opération.

## Phase 3 — Backend : endpoints

Dans `backend/routes/<domain>.py` (**à créer dans l'app dérivée**, puis enregistrer le router dans `backend/main.py`) :

```python
@router.post("/bulk-update", response_model=OrderBulkOperationResult)
async def bulk_update(
    payload: DomainBulkUpdateIn,
    user: TokenPayload = Depends(require_role("user")),  # adapter au rôle requis
    db: AsyncSession = Depends(get_db),
    # ... autres params filtres si nécessaire
):
    try:
        count = await crud.bulk_update_domains(db, ...)
        return OrderBulkOperationResult(success_count=count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Phase 4 — Frontend : mutations API

Le template n'a pas de couche `services/api.js` : les appels passent par le hook `useApiMutation` (invalidation de cache incluse).

```javascript
const bulkUpdateMutation = useApiMutation({
  endpoint: '/api/<domain>/bulk-update',
  method: 'POST',
  invalidateKeys: [['<domain>']],   // resynchronise la liste après l'opération
});

const bulkDeleteMutation = useApiMutation({
  endpoint: '/api/<domain>/bulk-delete',
  method: 'POST',
  invalidateKeys: [['<domain>']],
});

// Déclenchement au clic sur une action de masse :
// bulkUpdateMutation.mutate(buildBulkPayload({ set_status: '...' }))
```

## Phase 5 — Frontend : état de sélection + handlers

```javascript
// State
const [selectedItems, setSelectedItems] = useState([]);
const [selectAllMode, setSelectAllMode] = useState(false);
const [deselectedIds, setDeselectedIds] = useState(new Set());

// Compteur effectif
const effectiveSelectedCount = selectAllMode
  ? Math.max(0, totalRecords - deselectedIds.size)
  : selectedItems.length;

// Construction du payload — IDs ou params de filtre
const buildBulkPayload = (extra = {}) => {
  if (selectAllMode) {
    return {
      select_all: true,
      search: filters.search || undefined,
      year: filters.year || undefined,
      exclude_order_ids: deselectedIds.size > 0 ? [...deselectedIds] : undefined,
      ...extra,
    };
  }
  return { order_ids: selectedItems.map(o => o.id), ...extra };
};

// Handler de sélection — niveau page ou suivi désélection
const handleSelectionChange = (e) => {
  const value = e.value || [];
  if (selectAllMode) {
    const newDeselected = new Set(deselectedIds);
    const currentPageIds = new Set(items.map(o => o.id));
    const checkedIds = new Set(value.map(o => o.id));
    for (const id of currentPageIds) {
      checkedIds.has(id) ? newDeselected.delete(id) : newDeselected.add(id);
    }
    setDeselectedIds(newDeselected);
  } else {
    setSelectedItems(value);
  }
};
```

## Phase 6 — Frontend : colonne checkbox + batch bar

La table du socle (`frontend/src/components/ExampleList.jsx`) est une page concrète **sans sélection** : la colonne checkbox est **à ajouter dans l'app dérivée** (admin only) :

```jsx
{/* Header de la table */}
{isAdmin && <th style={{ width: '3rem' }} />}

{/* Cellule de chaque ligne — toggle dans selectedItems ou deselectedIds (cf. Phase 5) */}
{isAdmin && (
  <td>
    <input
      type="checkbox"
      checked={selectAllMode
        ? !deselectedIds.has(item.id)
        : selectedItems.some((s) => s.id === item.id)}
      onChange={() => toggleRow(item)}
    />
  </td>
)}
```

Batch action bar (affichée quand la sélection est active) :

```jsx
{isAdmin && (selectedItems.length > 0 || selectAllMode) && (
  <div className="batch-action-bar">
    <span>{effectiveSelectedCount} sélectionné(s)</span>
    {!selectAllMode && totalRecords > rowsPerPage && (
      <button onClick={() => { setSelectAllMode(true); setDeselectedIds(new Set()); }}>
        Sélectionner les {totalRecords} résultats filtrés
      </button>
    )}
    <button onClick={handleBulkAction}>Appliquer</button>
    <button onClick={clearSelection}>Désélectionner</button>
  </div>
)}
```

## Phase 7 — Vérification

1. Frontend build : `cd frontend && npm run build`
2. Python syntax check sur tous les fichiers modifiés
3. Tests manuels :
   - Cocher quelques checkboxes → batch bar avec compteur
   - Cliquer « Sélectionner les X filtrés » → tous sélectionnés, hint désélection
   - Naviguer vers une autre page → les checkboxes reflètent l'état select-all
   - Décocher un élément → exclu (compteur diminue)
   - Appliquer un bulk status change → tous les filtrés mis à jour
   - Appliquer un bulk delete → confirmation, tous les filtrés supprimés
   - Non-admin : pas de checkboxes, pas de batch bar

## Implementation References

> **Note** : ce template ne contient **pas** d'implémentation complète du bulk-operations. Les fichiers ci-dessous servent de patrons de structure ; le pattern complet (select-all filtré, bulk update/delete) est **à créer dans l'app dérivée** en suivant les phases ci-dessus.

| Référence | Chemin (existe dans le template) |
|---|---|
| Patron CRUD paginé backend (rôles, filtres, pagination) | `backend/routes/items.py` |
| Route de liste avec filtre simple | `backend/routes/test_data.py` |
| Schémas Pydantic (patrons `ItemResponse`, `PaginatedResponse`) | `backend/schemas.py` |
| Enregistrement des routers | `backend/main.py` |
| Page liste frontend (filtre + mutations optimistes) | `frontend/src/components/ExampleList.jsx` |
| Hooks API (`useApiQuery` / `useApiMutation`, invalidation de cache) | `frontend/src/hooks/useApiQuery.js`, `frontend/src/hooks/useApiMutation.js` |

## Conventions pour nouvelles pages

1. **Éviter le bulk update de statut** si le statut est calculé automatiquement (ex: statut de commande dérivé de la réception des articles). Préférer les opérations qui assignent des métadonnées (budget line, site, catégorie).
2. **Gater par `canWrite()` ou `isAdmin`** la colonne checkbox — ne jamais montrer de checkboxes à des users qui ne peuvent pas agir.
3. **Schéma bulk standard** : `DomainBulkUpdateIn` avec `ids` + `select_all` + params filtre + champs `set_*`.
4. **CRUD backend** : accepter à la fois `ids` (explicites) et `select_all` + params filtre, et supporter `exclude_*_ids` pour la désélection après « select all ».
5. **Toujours clear la sélection** sur changement de page, de filtre, de tri, et après une opération bulk réussie.

## Anti-patterns

| Pattern | Pourquoi c'est mal | Correction |
|---|---|---|
| Suivre `selectedIds` au lieu de `deselectedIds` en mode select-all | Impossible d'énumérer des milliers de lignes filtrées | Tracker les désélections, pas les sélections |
| `exclude_*_ids` ignoré côté backend | Les éléments décochés sont quand même modifiés/supprimés | Filtrer `target_ids` avant l'opération SQL |
| Bulk update sur un statut dérivé | Le statut recalculé écrase la modif au prochain cycle | Réserver le bulk aux métadonnées stables |
| Checkbox visible pour un user sans droits | UX trompeuse + sécurité | Gater par `isAdmin` / `canWrite()` |
