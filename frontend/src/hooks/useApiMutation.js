import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useConfig } from '../context/ConfigContext'
import { useAuth } from '../context/AuthContext'

/**
 * Hook wrapper autour de useMutation pour les mutations API (POST/PUT/DELETE).
 *
 * - Résout l'URL de base via ConfigContext
 * - Injecte le token Bearer automatiquement
 * - Applique des mises à jour optimistes avec rollback automatique en cas d'erreur
 * - Invalide les queryKeys spécifiées une fois la mutation terminée (succès OU erreur)
 *
 * Endpoint statique vs dynamique :
 * - String : `endpoint: '/api/test-data'` → mutate(bodyData)
 * - Function : `endpoint: ({ id }) => '/api/test-data/' + id` → mutate({ id, body: {...} })
 *   Quand endpoint est une fonction, le body JSON est extrait de `payload.body`.
 *
 * Mises à jour optimistes (norme du projet) :
 * - `optimisticUpdates` : tableau de `{ queryKey, updater }` appliqués avant l'appel réseau.
 *   `updater(oldData, payload)` doit retourner une NOUVELLE valeur immuable.
 *   En cas d'erreur, le snapshot pré-mutation est restauré automatiquement.
 * - `optimisticUpdate` : raccourci pour un seul `{ queryKey, updater }`.
 * - À la fin (succès ou échec), toutes les `invalidateKeys` ET les `queryKey` des updates
 *   optimistes sont invalidées pour resynchroniser avec le serveur.
 *
 * @param {Object} options
 * @param {string|Function} options.endpoint - Endpoint relatif ou fonction (payload) => endpoint
 * @param {string} [options.method='POST'] - Méthode HTTP
 * @param {Array<Array>} [options.invalidateKeys] - Liste de queryKeys à invalider après mutation
 * @param {{queryKey: Array, updater: Function}} [options.optimisticUpdate] - Patch optimiste sur une queryKey
 * @param {Array<{queryKey: Array, updater: Function}>} [options.optimisticUpdates] - Plusieurs patchs optimistes
 * @param {Object} [options.mutationOptions] - Options additionnelles passées à useMutation
 * @returns {import('@tanstack/react-query').UseMutationResult}
 */
export function useApiMutation({
  endpoint,
  method = 'POST',
  invalidateKeys = [],
  optimisticUpdate,
  optimisticUpdates,
  ...mutationOptions
}) {
  const config = useConfig()
  const { token } = useAuth()
  const queryClient = useQueryClient()

  // Normalise les patchs optimistes en un tableau unique
  const updates = []
  if (optimisticUpdate) updates.push(optimisticUpdate)
  if (Array.isArray(optimisticUpdates)) updates.push(...optimisticUpdates)

  const userOnMutate = mutationOptions.onMutate
  const userOnError = mutationOptions.onError
  const userOnSettled = mutationOptions.onSettled
  const userOnSuccess = mutationOptions.onSuccess
  const restMutationOptions = { ...mutationOptions }
  delete restMutationOptions.onMutate
  delete restMutationOptions.onError
  delete restMutationOptions.onSettled
  delete restMutationOptions.onSuccess

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

    // 1) Avant l'appel réseau : annule les fetchs en cours, snapshot et patch optimiste
    onMutate: async (payload) => {
      const snapshots = []

      for (const { queryKey, updater } of updates) {
        // Évite qu'un refetch concurrent écrase notre patch optimiste
        await queryClient.cancelQueries({ queryKey })
        const previous = queryClient.getQueryData(queryKey)
        snapshots.push({ queryKey, previous })
        queryClient.setQueryData(queryKey, (old) => updater(old, payload))
      }

      const userContext = userOnMutate ? await userOnMutate(payload) : undefined
      return { snapshots, userContext }
    },

    // 2) En cas d'erreur : rollback automatique vers le snapshot
    onError: (error, payload, context) => {
      if (context?.snapshots) {
        for (const { queryKey, previous } of context.snapshots) {
          queryClient.setQueryData(queryKey, previous)
        }
      }
      if (userOnError) userOnError(error, payload, context?.userContext)
    },

    // 3) Resynchronisation systématique avec le serveur (succès ou échec)
    onSettled: (data, error, payload, context) => {
      const keysToInvalidate = [
        ...invalidateKeys,
        ...updates.map((u) => u.queryKey),
      ]
      // Déduplique sur la sérialisation JSON pour éviter les invalidations multiples
      const seen = new Set()
      for (const key of keysToInvalidate) {
        const sig = JSON.stringify(key)
        if (seen.has(sig)) continue
        seen.add(sig)
        queryClient.invalidateQueries({ queryKey: key })
      }
      if (userOnSettled) userOnSettled(data, error, payload, context?.userContext)
    },

    onSuccess: userOnSuccess,

    ...restMutationOptions,
  })
}
