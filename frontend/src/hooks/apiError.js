/**
 * Normalise le champ `detail` d'une erreur API FastAPI en message affichable.
 *
 * FastAPI renvoie `detail` sous plusieurs formes :
 * - string (HTTPException classique)
 * - tableau d'objets de validation 422 ([{loc, msg, type}, ...]) —
 *   `new Error(detail)` produirait "[object Object]" à l'écran
 * - objet arbitraire ({msg: "..."} etc.)
 *
 * Porté du socle HUBsocle 2.23.2 (fix vague banc 2026-09-10).
 *
 * @param {*} detail - Champ `detail` de la réponse d'erreur
 * @param {string} fallback - Message si detail absent ou vide
 * @returns {string} Message lisible, toujours une string
 */
export function formatApiError(detail, fallback = 'Erreur inconnue') {
  if (detail === null || detail === undefined || detail === '') return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => formatApiError(d, '')).filter(Boolean)
    return parts.length ? parts.join(' ; ') : fallback
  }
  if (typeof detail === 'object') {
    if (detail.msg) return formatApiError(detail.msg, fallback)
    if (detail.message) return formatApiError(detail.message, fallback)
    try {
      return JSON.stringify(detail)
    } catch {
      return fallback
    }
  }
  return String(detail)
}
