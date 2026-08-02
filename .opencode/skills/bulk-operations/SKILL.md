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

Dans `app/schemas.py` :

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

Dans `app/crud.py`, extraire la logique de filtre dans une fonction réutilisable et ajouter :

```python
def list_domain_ids_by_filters(session, search, year, ...) -> List[int]:
    """Retourne tous les IDs matchant les filtres (sans pagination)."""
    conditions = _build_domain_filter_conditions(...)
    return session.exec(select(Domain.id).where(*conditions)).all()

def bulk_update_domains(session, order_ids=None, select_all=False,
                         exclude_order_ids=None, set_status=None, ...) -> int:
    if order_ids:
        target_ids = order_ids
    elif select_all:
        target_ids = list_domain_ids_by_filters(...)
    # Retirer les IDs explicitement désélectionnés
    if exclude_order_ids:
        target_ids = [id for id in target_ids if id not in set(exclude_order_ids)]
    if not target_ids:
        return 0
    stmt = update(Domain).where(Domain.id.in_(target_ids)).values(...)
    result = session.exec(stmt)
    session.commit()
    return result.rowcount
```

> **Invariant critique** : `exclude_order_ids` gère les éléments que l'utilisateur a explicitement décochés après « select all ». Le backend doit les filtrer avant l'opération.

## Phase 3 — Backend : endpoints

Dans `app/api/routes/<domain>.py` :

```python
@router.post("/bulk-update", response_model=OrderBulkOperationResult)
def bulk_update(payload: DomainBulkUpdateIn, ...):
    try:
        count = crud.bulk_update_domains(session, ...)
        return OrderBulkOperationResult(success_count=count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Phase 4 — Frontend : méthodes API

Dans `frontend/src/services/api.js` :

```javascript
bulkUpdate: async (data) => {
  const response = await api.post('/domain/bulk-update', data);
  return response.data;
},
bulkDelete: async (data) => {
  const response = await api.post('/domain/bulk-delete', data);
  return response.data;
},
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

## Phase 6 — Frontend : DataTable + batch bar

Colonne checkbox (admin only) :

```jsx
<AppDataTable
  selection={isAdmin ? selectedItems : undefined}
  onSelectionChange={isAdmin ? handleSelectionChange : undefined}
  ...
>
  {isAdmin && <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />}
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

| Référence | Chemin |
|---|---|
| Orders page (sélection + assignation budget line + bulk delete) | `frontend/src/pages/OrdersPage.jsx` |
| Orders backend CRUD | `app/crud.py::bulk_update_orders` / `bulk_delete_orders` |
| Orders backend routes | `app/api/routes/orders.py::POST /orders/bulk-update` / `POST /orders/bulk-delete` |
| Assets page (sélection + status change) | `frontend/src/pages/AssetsPage.jsx` |
| Assets backend CRUD | `app/crud.py::bulk_update_assets` |
| Assets backend routes | `app/api/routes/assets.py::POST /assets/bulk-update` |
| Schemas | `app/schemas.py::OrderBulkUpdateIn` / `OrderBulkDeleteIn` / `AssetBulkUpdateIn` / `OrderBulkOperationResult` |

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
