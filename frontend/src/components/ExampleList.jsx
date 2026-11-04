// SPDX-License-Identifier: MIT
// Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

/**
 * ExampleList — référence copiable de liste canonique CSS-first.
 * Structure : PageHeader (rendu par la page) → toolbar unique → hub-panel unique.
 * Données : GET /api/items → PaginatedResponse { items, total, page, per_page, pages }
 * (items : ItemResponse { id, title, description, is_public, owner, created_at, updated_at }).
 * Écritures : useApiMutation POST /api/items + DELETE /api/items/{id}, invalidation ['items'].
 */
import { useEffect, useState } from 'react'
import { useAuth } from '@poulidor/hub-socle/context/AuthContext.jsx'
import { useApiQuery } from '@poulidor/hub-socle/hooks/useApiQuery.js'
import { useApiMutation } from '@poulidor/hub-socle/hooks/useApiMutation.js'

const SPRITE = '/design-system/current/icons/lucide.svg'
const PER_PAGE = 5
const COLS = (canEdit) => (canEdit ? 6 : 5)

function ExampleList({ onTotal }) {
  const { isAuthenticated, hasMinRole } = useAuth()
  const canEdit = isAuthenticated && hasMinRole('user')

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [newItem, setNewItem] = useState({ title: '', description: '', is_public: false })

  // Comme l'ancien composant liste : pas de flag auth — le token est envoyé
  // s'il est disponible (endpoint à auth optionnelle : publics seuls, ou publics + siens).
  const { data, isLoading, error } = useApiQuery({
    queryKey: ['items', page],
    endpoint: '/api/items',
    params: { page, per_page: PER_PAGE },
  })

  // Remonte le total au PageHeader de la page (une seule requête pour tout).
  useEffect(() => {
    onTotal?.(data?.total ?? null)
  }, [data?.total, onTotal])

  // Ramène la page courante dans les bornes si un delete vide la dernière page.
  useEffect(() => {
    if (data && data.pages > 0 && page > data.pages) setPage(data.pages)
  }, [data, page])

  // Écritures : simple invalidation du préfixe ['items'] (toutes les pages).
  const createMutation = useApiMutation({
    endpoint: '/api/items',
    method: 'POST',
    invalidateKeys: [['items']],
  })
  const deleteMutation = useApiMutation({
    endpoint: ({ id }) => `/api/items/${id}`,
    method: 'DELETE',
    invalidateKeys: [['items']],
  })

  const items = data?.items || []
  const pages = data?.pages || 1
  const actionPending = createMutation.isPending || deleteMutation.isPending
  const fetchError = error?.message || createMutation.error?.message
    || deleteMutation.error?.message || null

  // Recherche locale (titre + description) sur la page courante.
  const needle = search.trim().toLowerCase()
  const visible = needle
    ? items.filter((i) => `${i.title} ${i.description ?? ''}`.toLowerCase().includes(needle))
    : items

  const handleCreate = (e) => {
    e.preventDefault()
    if (!newItem.title.trim()) return
    createMutation.mutate(newItem, {
      onSuccess: () => {
        setNewItem({ title: '', description: '', is_public: false })
        setShowAddForm(false)
      },
    })
  }

  // Toolbar unique : en création, elle devient le mini-formulaire inline.
  const toolbar = canEdit && showAddForm ? (
    <form className="hub-toolbar" onSubmit={handleCreate}>
      <input className="hub-input" placeholder="Titre *" required aria-label="Titre"
        value={newItem.title}
        onChange={(e) => setNewItem({ ...newItem, title: e.target.value })} />
      <input className="hub-input" placeholder="Description" aria-label="Description"
        value={newItem.description}
        onChange={(e) => setNewItem({ ...newItem, description: e.target.value })} />
      <label>
        <input type="checkbox" checked={newItem.is_public}
          onChange={(e) => setNewItem({ ...newItem, is_public: e.target.checked })} /> Public
      </label>
      <button type="submit" className="hub-button" disabled={actionPending}>Créer</button>
      <button type="button" className="hub-button hub-button-secondary"
        onClick={() => setShowAddForm(false)}>Annuler</button>
    </form>
  ) : (
    <div className="hub-toolbar">
      <input type="search" className="hub-input" placeholder="Rechercher…" aria-label="Rechercher un élément"
        value={search} onChange={(e) => setSearch(e.target.value)} />
      {canEdit && (
        <button type="button" className="hub-button" onClick={() => setShowAddForm(true)}>
          Ajouter
        </button>
      )}
    </div>
  )

  return (
    <>
      {toolbar}
      <div className="hub-panel">
        {fetchError && <div className="data-error" role="alert">{fetchError}</div>}

        <table className="hub-table hub-table--striped">
          <thead>
            <tr>
              <th>Titre</th><th>Description</th><th>Public</th><th>Propriétaire</th><th>Créé le</th>
              {canEdit && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: PER_PAGE }).map((_, r) => (
                <tr key={`sk-${r}`}>
                  {Array.from({ length: COLS(canEdit) }).map((_, c) => (
                    <td key={c}><div className="hub-skeleton-text"><div className="hub-skeleton" /></div></td>
                  ))}
                </tr>
              ))
              : visible.map((item) => (
                <tr key={item.id}>
                  <td>{item.title}</td>
                  <td>{item.description || '—'}</td>
                  <td>{item.is_public ? 'Oui' : 'Non'}</td>
                  <td>{item.owner}</td>
                  <td>{new Date(item.created_at).toLocaleDateString('fr-FR')}</td>
                  {canEdit && (
                    <td>
                      <button type="button" className="hub-icon-button" title="Supprimer"
                        aria-label={`Supprimer ${item.title}`} disabled={deleteMutation.isPending}
                        onClick={() => deleteMutation.mutate({ id: item.id })}>
                        <svg className="hub-icon" aria-hidden="true"><use href={`${SPRITE}#icon-trash-2`} /></svg>
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            {!isLoading && visible.length === 0 && (
              <tr>
                <td colSpan={COLS(canEdit)}>
                  <div className="hub-empty-state">
                    <div className="hub-empty-state-icon">
                      <svg className="hub-icon" aria-hidden="true"><use href={`${SPRITE}#icon-inbox`} /></svg>
                    </div>
                    <p className="hub-empty-state-title">Aucun élément</p>
                    <p className="hub-empty-state-description">
                      {needle ? `Aucun résultat pour « ${search.trim()} ».` : 'Ajoutez un premier élément via la toolbar.'}
                    </p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {/* Pagination minimale ‹ › */}
        <div className="example-list-footer">
          <button type="button" className="hub-button hub-button--sm hub-button-secondary"
            disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Page précédente">‹</button>
          <span>Page {page} / {pages}</span>
          <button type="button" className="hub-button hub-button--sm hub-button-secondary"
            disabled={page >= pages} onClick={() => setPage((p) => p + 1)} aria-label="Page suivante">›</button>
        </div>
      </div>
    </>
  )
}

export default ExampleList
