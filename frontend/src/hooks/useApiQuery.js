import { useQuery } from '@tanstack/react-query'
import { useConfig } from '../context/ConfigContext'
import { useAuth } from '../context/AuthContext'

/**
 * Hook wrapper autour de useQuery pour les appels API.
 *
 * - Résout l'URL de base via ConfigContext
 * - Injecte le token Bearer si disponible
 * - Accepte un endpoint relatif (ex: '/api/items')
 *
 * @param {Object} options
 * @param {string[]} options.queryKey - Clé de cache TanStack Query (ex: ['items', filterCategory])
 * @param {string} options.endpoint - Endpoint relatif (ex: '/api/test-data')
 * @param {Object} [options.params] - Query params à ajouter à l'URL
 * @param {boolean} [options.auth=false] - Forcer l'envoi du token (sinon envoyé si disponible)
 * @param {Object} [options.queryOptions] - Options additionnelles passées à useQuery
 * @returns {import('@tanstack/react-query').UseQueryResult}
 */
export function useApiQuery({ queryKey, endpoint, params, auth = false, ...queryOptions }) {
  const config = useConfig()
  const { token } = useAuth()

  return useQuery({
    queryKey,
    queryFn: async () => {
      let url = `${config.apiUrl}${endpoint}`

      if (params) {
        const searchParams = new URLSearchParams()
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined && value !== null && value !== '') {
            searchParams.set(key, value)
          }
        })
        const qs = searchParams.toString()
        if (qs) url += `?${qs}`
      }

      const headers = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch(url, { headers })

      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || `Erreur ${response.status}`)
      }

      return response.json()
    },
    enabled: Boolean(config.apiUrl) && (!auth || Boolean(token)),
    ...queryOptions,
  })
}
