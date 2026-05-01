# Data Fetching — TanStack Query (React Query)

Ce document décrit les patterns obligatoires pour le data fetching dans le frontend React de cette application.

## Pourquoi TanStack Query

L'application utilise **TanStack Query v5** (anciennement React Query) pour toutes les interactions avec l'API. Cette librairie gère automatiquement :

- **Le cache** : les données récupérées sont mises en cache par `queryKey`. Deux composants qui demandent la même donnée ne déclenchent qu'une seule requête réseau.
- **Stale-while-revalidate** : les données périmées sont affichées immédiatement pendant qu'un rafraîchissement s'effectue en arrière-plan.
- **L'invalidation** : après une mutation (POST/PUT/DELETE), on invalide les `queryKeys` concernées et TanStack Query rafraîchit automatiquement les données sans rechargement de page.
- **Le polling** : certaines données (ex: statut Hub) sont rafraîchies à intervalle régulier via `refetchInterval`.
- **La déduplication** : si plusieurs composants demandent les mêmes données au même moment, une seule requête réseau est faite.

## Architecture

```
QueryClientProvider (main.jsx)
  └─ queryClient (src/lib/queryClient.js) — configuration globale
       ├─ useApiQuery  (src/hooks/useApiQuery.js)  — lectures (GET)
       └─ useApiMutation (src/hooks/useApiMutation.js) — mutations (POST/PUT/DELETE)
```

Le `QueryClientProvider` englobe toute l'application (dans `main.jsx`), après `AuthProvider` pour que les hooks aient accès au token d'authentification.

### Configuration par défaut (queryClient.js)

| Option | Valeur | Description |
|--------|--------|-------------|
| `staleTime` | 30 secondes | Durée pendant laquelle les données sont considérées "fraîches" |
| `retry` | 1 | Nombre de tentatives après échec |
| `refetchOnWindowFocus` | true | Rafraîchit quand l'utilisateur revient sur l'onglet |

## Hooks utilitaires

### `useApiQuery` — Lecture de données (GET)

```jsx
import { useApiQuery } from '../hooks/useApiQuery'

// Lecture simple
const { data, isLoading, error } = useApiQuery({
  queryKey: ['items'],
  endpoint: '/api/items',
})

// Lecture avec paramètres de filtre (queryKey dynamique)
const { data, isLoading } = useApiQuery({
  queryKey: ['items', category, page],
  endpoint: '/api/items',
  params: { category, page, per_page: 20 },
})

// Lecture avec polling (rafraîchissement automatique)
const { data } = useApiQuery({
  queryKey: ['hub-status'],
  endpoint: '/api/health/detailed',
  refetchInterval: 15000,   // toutes les 15 secondes
  retry: false,              // pas de retry pour le health check
})

// Lecture conditionnelle (seulement si authentifié)
const { data } = useApiQuery({
  queryKey: ['preferences'],
  endpoint: '/api/preferences',
  auth: true,   // désactive la query si pas de token
})
```

En pratique, `useApiQuery` attend aussi que `config.apiUrl` soit disponible via `ConfigContext`. Tant que `/api/config` n'a pas été chargé, la query reste désactivée même si `auth` vaut `false`.

**Paramètres :**

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `queryKey` | `string[]` | ✅ | Clé de cache unique. Doit inclure tous les paramètres variables |
| `endpoint` | `string` | ✅ | Endpoint API relatif (ex: `/api/items`) |
| `params` | `object` | | Query parameters ajoutés à l'URL |
| `auth` | `boolean` | | Si `true`, désactive la query quand il n'y a pas de token |
| `...options` | | | Toute option valide de `useQuery` (staleTime, refetchInterval, enabled, etc.) |

Note d'execution : le hook active la query seulement si `config.apiUrl` est defini, puis applique la condition d'authentification. Le comportement reel est donc :

```jsx
enabled: Boolean(config.apiUrl) && (!auth || Boolean(token))
```

### `useApiMutation` — Mutations (POST/PUT/DELETE)

> **Norme du projet** : toute mutation qui modifie une liste/objet déjà affiché doit utiliser le pattern **optimistic update + rollback automatique** via `optimisticUpdate` (ou `optimisticUpdates`).
> L'invalidation seule via `invalidateKeys` reste autorisée uniquement quand l'UI ne dépend pas de la donnée à jour (ex : action déclenchant un job, seed dont la forme côté serveur n'est pas connue).

```jsx
import { useApiMutation } from '../hooks/useApiMutation'

const listQueryKey = ['items', filter]

// Création — ajoute immédiatement un item temporaire en cache, rollback si erreur
const createMutation = useApiMutation({
  endpoint: '/api/items',
  method: 'POST',
  optimisticUpdate: {
    queryKey: listQueryKey,
    updater: (old, payload) => ({
      ...(old || {}),
      items: [
        ...(old?.items || []),
        { id: `__tmp_${Date.now()}`, ...payload, __optimistic: true },
      ],
    }),
  },
})
// Usage : createMutation.mutate({ name: 'Mon item', value: '42' })

// Mise à jour (endpoint dynamique avec ID)
const updateMutation = useApiMutation({
  endpoint: ({ id }) => `/api/items/${id}`,
  method: 'PUT',
  optimisticUpdate: {
    queryKey: listQueryKey,
    updater: (old, { id, body }) => ({
      ...(old || {}),
      items: (old?.items || []).map((item) =>
        item.id === id ? { ...item, ...body } : item
      ),
    }),
  },
})
// Usage : updateMutation.mutate({ id: 5, body: { name: 'Nouveau nom' } })

// Suppression
const deleteMutation = useApiMutation({
  endpoint: ({ id }) => `/api/items/${id}`,
  method: 'DELETE',
  optimisticUpdate: {
    queryKey: listQueryKey,
    updater: (old, { id }) => ({
      ...(old || {}),
      items: (old?.items || []).filter((item) => item.id !== id),
    }),
  },
})
// Usage : deleteMutation.mutate({ id: 5 })

// Action sans état affiché (seed, job, etc.) — simple invalidation acceptée
const seedMutation = useApiMutation({
  endpoint: '/api/test-data/seed',
  method: 'POST',
  invalidateKeys: [['test-data']],
})
```

**Comportement automatique du hook :**

1. `onMutate` : annule les fetchs en cours, snapshot l'état du cache, applique l'`updater`.
2. `onError` : restaure le snapshot (rollback automatique).
3. `onSettled` (succès OU échec) : invalide les `queryKey` patchées **et** les `invalidateKeys` pour resynchroniser avec le serveur.

**Règles pour l'`updater` :**

- Doit retourner une **nouvelle référence** (spread, `map`, `filter`) — jamais muter `old`.
- Doit accepter un `old` potentiellement `undefined` (si la query n'a pas encore chargé).
- Reçoit le payload exact passé à `mutate(...)` (donc `{ id, body }` pour les endpoints dynamiques).

**Pour patcher plusieurs caches dans la même mutation :**

```jsx
useApiMutation({
  endpoint: ({ id }) => `/api/items/${id}`,
  method: 'PUT',
  optimisticUpdates: [
    { queryKey: ['items'], updater: (old, { id, body }) => /* ... */ },
    { queryKey: ['items', id], updater: (old, { body }) => ({ ...old, ...body }) },
  ],
})
```

**Paramètres :**

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `endpoint` | `string \| Function` | ✅ | Statique (`'/api/items'`) ou dynamique (`({ id }) => '/api/items/' + id`) |
| `method` | `string` | | `'POST'` par défaut. Aussi `'PUT'`, `'DELETE'`, `'PATCH'` |
| `optimisticUpdate` | `{ queryKey, updater }` | | Patch optimiste sur une queryKey (norme). `updater(old, payload)` doit retourner une nouvelle référence immuable. Rollback automatique en cas d'erreur. |
| `optimisticUpdates` | `Array<{ queryKey, updater }>` | | Même chose pour plusieurs caches en parallèle. |
| `invalidateKeys` | `string[][]` | | Invalidations supplémentaires à déclencher en fin de mutation (succès OU échec). Les `queryKey` des updates optimistes sont déjà invalidées automatiquement. |
| `...options` | | | Toute option valide de `useMutation` (`onSuccess`, `onError`, `onSettled`, etc.) |

**Convention endpoint dynamique :**
- Quand `endpoint` est une **fonction**, elle reçoit le payload complet passé à `mutate()`
- Le body JSON est alors extrait de `payload.body`
- Quand `endpoint` est une **string**, le payload entier est envoyé comme body JSON

**États de la mutation :**

```jsx
const mutation = useApiMutation({ ... })

mutation.isPending  // true pendant l'exécution
mutation.isError    // true si erreur
mutation.error      // l'objet Error
mutation.isSuccess  // true si succès
mutation.data       // la réponse du serveur
mutation.reset()    // réinitialiser l'état
```

**Callbacks inline :**

```jsx
mutation.mutate(data, {
  onSuccess: (result) => {
    // Reset du formulaire, fermer un modal, etc.
    setShowForm(false)
  },
  onError: (error) => {
    // Notification d'erreur spécifique
    console.error(error.message)
  },
})
```

## Convention des queryKeys

Les queryKeys doivent suivre une convention hiérarchique :

```
['domaine']                           → liste complète
['domaine', filtre1, filtre2]         → liste filtrée
['domaine', id]                       → élément unique
```

### Référence des queryKeys par domaine

| Domaine | queryKey | Endpoint |
|---------|----------|----------|
| Test data | `['test-data']` | `GET /api/test-data` |
| Test data filtré | `['test-data', category]` | `GET /api/test-data?category=...` |
| Items | `['items']` | `GET /api/items` |
| Items paginés | `['items', page, perPage, category]` | `GET /api/items?page=...` |
| Item unique | `['items', id]` | `GET /api/items/{id}` |
| Préférences | `['preferences']` | `GET /api/preferences` |
| Statut Hub | `['hub-status']` | `GET /api/health/detailed` |

> **Important** : quand vous invalidez, utilisez un préfixe partiel pour invalider toutes les variantes.
> `invalidateQueries({ queryKey: ['items'] })` invalide `['items']`, `['items', 1]`, `['items', 2, 20, 'general']`, etc.

## Exemple complet — Composant CRUD

```jsx
import React, { useState } from 'react'
import { useApiQuery } from '../hooks/useApiQuery'
import { useApiMutation } from '../hooks/useApiMutation'

function ItemList() {
  const [page, setPage] = useState(1)
  const listQueryKey = ['items', page]

  // Lecture avec pagination
  const { data, isLoading, error } = useApiQuery({
    queryKey: listQueryKey,
    endpoint: '/api/items',
    params: { page, per_page: 20 },
  })

  // Création optimiste
  const createMutation = useApiMutation({
    endpoint: '/api/items',
    method: 'POST',
    optimisticUpdate: {
      queryKey: listQueryKey,
      updater: (old, payload) => ({
        ...(old || {}),
        items: [
          ...(old?.items || []),
          { id: `__tmp_${Date.now()}`, ...payload, __optimistic: true },
        ],
      }),
    },
  })

  // Suppression optimiste (endpoint dynamique)
  const deleteMutation = useApiMutation({
    endpoint: ({ id }) => `/api/items/${id}`,
    method: 'DELETE',
    optimisticUpdate: {
      queryKey: listQueryKey,
      updater: (old, { id }) => ({
        ...(old || {}),
        items: (old?.items || []).filter((item) => item.id !== id),
      }),
    },
  })

  if (isLoading) return <p>Chargement...</p>
  if (error) return <p>Erreur : {error.message}</p>

  return (
    <div>
      {data.items.map(item => (
        <div key={item.id} style={{ opacity: item.__optimistic ? 0.6 : 1 }}>
          {item.name}
          <button
            onClick={() => deleteMutation.mutate({ id: item.id })}
            disabled={deleteMutation.isPending || item.__optimistic}
          >
            Supprimer
          </button>
        </div>
      ))}
      <button onClick={() => setPage(p => p + 1)}>Page suivante</button>
    </div>
  )
}
```

## Anti-patterns à éviter

### ❌ Ne pas faire : fetch + useState + useEffect manuels

```jsx
// ❌ INTERDIT — ne plus utiliser ce pattern
const [data, setData] = useState([])
const [loading, setLoading] = useState(true)

useEffect(() => {
  fetch('/api/items')
    .then(res => res.json())
    .then(data => setData(data))
    .finally(() => setLoading(false))
}, [])
```

### ✅ Faire à la place : useApiQuery

```jsx
// ✅ CORRECT — utilise le cache, la déduplication, le retry, etc.
const { data, isLoading } = useApiQuery({
  queryKey: ['items'],
  endpoint: '/api/items',
})
```

### ❌ Ne pas oublier d'invalider après une mutation

```jsx
// ❌ PROBLÈME — les données affichées ne se mettent pas à jour
const mutation = useApiMutation({
  endpoint: '/api/items',
  method: 'POST',
  // ni optimisticUpdate ni invalidateKeys !
})
```

### ✅ Toujours préférer un `optimisticUpdate` (norme), `invalidateKeys` en repli

```jsx
// ✅ CORRECT — UI mise à jour instantanément, rollback automatique si erreur
const mutation = useApiMutation({
  endpoint: '/api/items',
  method: 'POST',
  optimisticUpdate: {
    queryKey: ['items'],
    updater: (old, payload) => ({
      ...(old || {}),
      items: [...(old?.items || []), { id: `__tmp_${Date.now()}`, ...payload }],
    }),
  },
})
```

### ❌ Ne pas muter `old` dans un updater optimiste

```jsx
// ❌ PROBLÈME — modifie le cache en place, React ne re-rendra pas
updater: (old, { id }) => {
  old.items.splice(old.items.findIndex(i => i.id === id), 1)
  return old
}
```

### ✅ Toujours retourner une nouvelle référence immuable

```jsx
updater: (old, { id }) => ({
  ...(old || {}),
  items: (old?.items || []).filter(item => item.id !== id),
})
```

### ❌ Ne pas mettre de données variables hors de la queryKey

```jsx
// ❌ PROBLÈME — le cache ne distingue pas les filtres
const { data } = useApiQuery({
  queryKey: ['items'],           // manque le filtre !
  endpoint: '/api/items',
  params: { category: filter },
})
```

### ✅ Inclure toutes les variables dans la queryKey

```jsx
// ✅ CORRECT — chaque combinaison a son propre cache
const { data } = useApiQuery({
  queryKey: ['items', filter],
  endpoint: '/api/items',
  params: { category: filter },
})
```

## DevTools

En développement, les **React Query DevTools** sont disponibles (icône flottante en bas à gauche). Elles permettent de :

- Voir toutes les queryKeys actives et leur état (fresh, stale, fetching)
- Inspecter les données en cache
- Déclencher manuellement un refetch ou une invalidation
- Voir l'historique des mutations

Les DevTools ne sont pas incluses dans le build de production.
