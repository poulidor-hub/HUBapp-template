import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useConfig } from '../context/ConfigContext'
import { useAuth } from '../context/AuthContext'

/**
 * Hook wrapper autour de useMutation pour les mutations API (POST/PUT/DELETE).
 *
 * - Résout l'URL de base via ConfigContext
 * - Injecte le token Bearer automatiquement
 * - Invalide les queryKeys spécifiées après succès
 *
 * Endpoint statique vs dynamique :
 * - String : `endpoint: '/api/test-data'` → mutate(bodyData)
 * - Function : `endpoint: ({ id }) => '/api/test-data/' + id` → mutate({ id, body: {...} })
 *   Quand endpoint est une fonction, le body JSON est extrait de `payload.body`.
 *
 * @param {Object} options
 * @param {string|Function} options.endpoint - Endpoint relatif ou fonction (payload) => endpoint
 * @param {string} [options.method='POST'] - Méthode HTTP
 * @param {string[][]} [options.invalidateKeys] - Liste de queryKeys à invalider après succès
 * @param {Object} [options.mutationOptions] - Options additionnelles passées à useMutation
 * @returns {import('@tanstack/react-query').UseMutationResult}
 */
export function useApiMutation({ endpoint, method = 'POST', invalidateKeys = [], ...mutationOptions }) {
  const config = useConfig()
  const { token } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (payload) => {
      let resolvedEndpoint, body

      if (typeof endpoint === 'function') {
        resolvedEndpoint = endpoint(payload)
        body = payload?.body
      } else {
        resolvedEndpoint = endpoint
        body = payload
      }

      const url = `${config.apiUrl}${resolvedEndpoint}`

      const headers = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const fetchOptions = { method, headers }

      if (body !== undefined && body !== null) {
        headers['Content-Type'] = 'application/json'
        fetchOptions.body = JSON.stringify(body)
      }

      const response = await fetch(url, fetchOptions)

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}))
        throw new Error(errBody.detail || `Erreur ${response.status}`)
      }

      // Certaines réponses 204 n'ont pas de body
      const text = await response.text()
      return text ? JSON.parse(text) : null
    },
    onSuccess: () => {
      invalidateKeys.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key })
      })
    },
    ...mutationOptions,
  })
}
