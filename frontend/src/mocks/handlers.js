import { http, HttpResponse, delay } from 'msw'

/**
 * Handlers MSW — MIROIR du backend réel (voir backend/routes/ et backend/schemas.py).
 *
 * Ce fichier est le CONTRAT D'APPRENTISSAGE du template : tout client codé
 * contre ces mocks doit fonctionner identiquement contre le backend Docker.
 * ⚠️ Toute modification du backend doit être répercutée ici (et inversement).
 *
 * Aligné sur :
 * - GET  /api/items          → PaginatedResponse {items, total, page, per_page, pages}
 * - POST /api/items          → ItemCreate  {title, description?, is_public} → 201 ItemResponse
 * - GET  /api/items/:id      → ItemResponse | 404 {detail}
 * - PUT  /api/items/:id      → ItemUpdate  → ItemResponse
 * - DELETE /api/items/:id    → 204
 * - GET  /api/test-data      → TestDataListResponse {items, total}
 * - POST /api/test-data      → TestDataCreate {name, value?, category} → 201 TestDataResponse
 * - GET  /api/health         → {status, app, version, hub_connected}
 */

// Store en mémoire (réinitialisé à chaque rechargement en dev)
const db = {
  items: [
    {
      id: 1,
      title: 'Item Alpha',
      description: 'Premier item de démonstration',
      is_public: true,
      owner: 'demo-user',
      created_at: '2026-01-15T09:00:00Z',
      updated_at: '2026-01-15T09:00:00Z',
    },
    {
      id: 2,
      title: 'Item Beta',
      description: null,
      is_public: false,
      owner: 'demo-user',
      created_at: '2026-01-16T10:30:00Z',
      updated_at: '2026-01-16T10:30:00Z',
    },
    {
      id: 3,
      title: 'Item Gamma',
      description: 'Item public avec description',
      is_public: true,
      owner: 'demo-admin',
      created_at: '2026-01-17T14:00:00Z',
      updated_at: '2026-01-17T14:00:00Z',
    },
  ],
  test_data: [
    { id: 1, name: 'Exemple', value: 'Valeur de démonstration', category: 'general', last_modified_by: 'demo-user', created_at: '2026-01-15T09:00:00Z', updated_at: '2026-01-15T09:00:00Z' },
  ],
  next_id: { items: 4, test_data: 2 },
}

const nowIso = () => new Date().toISOString()

export const handlers = [
  http.get('/api/health', () => {
    return HttpResponse.json({
      status: 'healthy',
      app: 'mock-app',
      version: '0.0.0',
      hub_connected: true,
    })
  }),

  // ===== Items (contrat : backend/routes/items.py + schemas.py) =====

  http.get('/api/items', async ({ request }) => {
    await delay(150)
    const url = new URL(request.url)
    const page = Math.max(1, Number(url.searchParams.get('page') ?? 1))
    const per_page = Math.min(100, Math.max(1, Number(url.searchParams.get('per_page') ?? 20)))
    const all = db.items
    const start = (page - 1) * per_page
    const slice = all.slice(start, start + per_page)
    return HttpResponse.json({
      items: slice,
      total: all.length,
      page,
      per_page,
      pages: Math.ceil(all.length / per_page) || 1,
    })
  }),

  http.post('/api/items', async ({ request }) => {
    const body = await request.json()
    // Validation minimale reflétant ItemCreate (title requis, 1-255)
    if (!body.title || typeof body.title !== 'string' || body.title.length > 255) {
      return HttpResponse.json(
        { detail: [{ loc: ['body', 'title'], msg: 'title requis (1-255 caractères)' }] },
        { status: 422 },
      )
    }
    const item = {
      id: db.next_id.items++,
      title: body.title,
      description: body.description ?? null,
      is_public: body.is_public ?? false,
      owner: 'demo-user',
      created_at: nowIso(),
      updated_at: nowIso(),
    }
    db.items.push(item)
    return HttpResponse.json(item, { status: 201 })
  }),

  http.get('/api/items/:id', async ({ params }) => {
    const item = db.items.find((i) => i.id === Number(params.id))
    if (!item) {
      return HttpResponse.json({ detail: 'Item non trouvé' }, { status: 404 })
    }
    return HttpResponse.json(item)
  }),

  http.put('/api/items/:id', async ({ params, request }) => {
    const item = db.items.find((i) => i.id === Number(params.id))
    if (!item) {
      return HttpResponse.json({ detail: 'Item non trouvé' }, { status: 404 })
    }
    const body = await request.json()
    if (body.title !== undefined) item.title = body.title
    if (body.description !== undefined) item.description = body.description
    if (body.is_public !== undefined) item.is_public = body.is_public
    item.updated_at = nowIso()
    return HttpResponse.json(item)
  }),

  http.delete('/api/items/:id', async ({ params }) => {
    const idx = db.items.findIndex((i) => i.id === Number(params.id))
    if (idx === -1) {
      return HttpResponse.json({ detail: 'Item non trouvé' }, { status: 404 })
    }
    db.items.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ===== Test data (contrat : backend/routes/test_data.py) =====

  http.get('/api/test-data', async () => {
    await delay(100)
    return HttpResponse.json({ items: db.test_data, total: db.test_data.length })
  }),

  http.post('/api/test-data', async ({ request }) => {
    const body = await request.json()
    if (!body.name || typeof body.name !== 'string') {
      return HttpResponse.json(
        { detail: [{ loc: ['body', 'name'], msg: 'name requis' }] },
        { status: 422 },
      )
    }
    const entry = {
      id: db.next_id.test_data++,
      name: body.name,
      value: body.value ?? null,
      category: body.category ?? 'general',
      last_modified_by: 'demo-user',
      created_at: nowIso(),
      updated_at: nowIso(),
    }
    db.test_data.push(entry)
    return HttpResponse.json(entry, { status: 201 })
  }),
]
