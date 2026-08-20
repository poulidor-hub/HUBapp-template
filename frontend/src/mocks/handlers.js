import { http, HttpResponse, delay } from 'msw'

export const handlers = [
  http.get('/api/health', () => {
    return HttpResponse.json({
      status: 'healthy',
      app: 'mock-app',
      version: '0.0.1',
      hub_connected: true,
    })
  }),

  http.get('/api/items', async () => {
    await delay(150)
    return HttpResponse.json([
      { id: 1, name: 'Item Alpha', status: 'active' },
      { id: 2, name: 'Item Beta', status: 'pending' },
      { id: 3, name: 'Item Gamma', status: 'active' },
    ])
  }),

  http.post('/api/items', async ({ request }) => {
    const body = await request.json()
    return HttpResponse.json({ id: 99, ...body }, { status: 201 })
  }),

  http.get('/api/items/999', () => {
    return HttpResponse.json(
      { detail: 'Item not found' },
      { status: 404 }
    )
  }),
]
