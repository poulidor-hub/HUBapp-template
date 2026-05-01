import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useApiQuery } from '../hooks/useApiQuery'
import { useApiMutation } from '../hooks/useApiMutation'

// Catégories disponibles
const CATEGORIES = ['general', 'infrastructure', 'stack', 'config', 'custom']

function DataTable() {
  const { token, isAuthenticated, hasMinRole } = useAuth()
  
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', value: '', category: 'general' })
  const [newForm, setNewForm] = useState({ name: '', value: '', category: 'general' })
  const [showAddForm, setShowAddForm] = useState(false)
  const [filterCategory, setFilterCategory] = useState('')

  // Lecture des données via TanStack Query
  const {
    data: queryData,
    isLoading: loading,
    error: queryError,
    refetch,
  } = useApiQuery({
    queryKey: ['test-data', filterCategory],
    endpoint: '/api/test-data',
    params: filterCategory ? { category: filterCategory } : undefined,
  })

  const data = queryData?.items || []
  const error = queryError?.message || null

  // QueryKey courante (incluant le filtre) pour cibler les patchs optimistes
  const listQueryKey = ['test-data', filterCategory]

  // Mutations CRUD — pattern norme du projet : update optimiste + rollback automatique.
  // useApiMutation invalide aussi le cache à la fin (succès OU échec) pour resynchroniser.
  const createMutation = useApiMutation({
    endpoint: '/api/test-data',
    method: 'POST',
    optimisticUpdate: {
      queryKey: listQueryKey,
      updater: (old, payload) => {
        const optimisticItem = {
          id: `__tmp_${Date.now()}`,
          name: payload.name,
          value: payload.value,
          category: payload.category,
          last_modified_by: 'vous',
          updated_at: new Date().toISOString(),
          __optimistic: true,
        }
        return { ...(old || {}), items: [...(old?.items || []), optimisticItem] }
      },
    },
  })

  const updateMutation = useApiMutation({
    endpoint: ({ id }) => `/api/test-data/${id}`,
    method: 'PUT',
    optimisticUpdate: {
      queryKey: listQueryKey,
      updater: (old, { id, body }) => ({
        ...(old || {}),
        items: (old?.items || []).map((item) =>
          item.id === id ? { ...item, ...body, updated_at: new Date().toISOString() } : item
        ),
      }),
    },
  })

  const deleteMutation = useApiMutation({
    endpoint: ({ id }) => `/api/test-data/${id}`,
    method: 'DELETE',
    optimisticUpdate: {
      queryKey: listQueryKey,
      updater: (old, { id }) => ({
        ...(old || {}),
        items: (old?.items || []).filter((item) => item.id !== id),
      }),
    },
  })

  // Pas d'optimistic ici : seed crée des données côté serveur dont on ne connaît pas la forme.
  // On laisse la simple invalidation rafraîchir la liste.
  const seedMutation = useApiMutation({
    endpoint: '/api/test-data/seed',
    method: 'POST',
    invalidateKeys: [['test-data']],
  })

  const actionLoading = createMutation.isPending || updateMutation.isPending
    || deleteMutation.isPending || seedMutation.isPending

  const mutationError = createMutation.error?.message || updateMutation.error?.message
    || deleteMutation.error?.message || seedMutation.error?.message || null

  // Créer une entrée
  const handleCreate = (e) => {
    e.preventDefault()
    if (!token || !newForm.name.trim()) return
    
    createMutation.mutate(newForm, {
      onSuccess: () => {
        setNewForm({ name: '', value: '', category: 'general' })
        setShowAddForm(false)
      },
    })
  }

  // Mettre à jour une entrée
  const handleUpdate = (id) => {
    if (!token) return
    
    updateMutation.mutate({ id, body: editForm }, {
      onSuccess: () => setEditingId(null),
    })
  }

  // Supprimer une entrée
  const handleDelete = (id) => {
    if (!token) return
    if (!confirm('Êtes-vous sûr de vouloir supprimer cette entrée ?')) return
    
    deleteMutation.mutate({ id })
  }

  // Initialiser des données de test
  const handleSeed = () => {
    if (!token) return
    seedMutation.mutate(null)
  }

  // Commencer l'édition
  const startEdit = (item) => {
    setEditingId(item.id)
    setEditForm({
      name: item.name,
      value: item.value || '',
      category: item.category
    })
  }

  // Annuler l'édition
  const cancelEdit = () => {
    setEditingId(null)
    setEditForm({ name: '', value: '', category: 'general' })
  }

  // Formater la date
  const formatDate = (dateString) => {
    if (!dateString) return '-'
    const date = new Date(dateString)
    return date.toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  // Vérifie si l'utilisateur peut modifier (rôle user+)
  const canEdit = isAuthenticated && hasMinRole('user')

  return (
    <div className="card">
      <h2>📊 Données de Test (Backup)</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '15px' }}>
        Tableau de données partagées pour tester le système de backup.
        {!isAuthenticated && " Connectez-vous pour modifier les données."}
      </p>

      {/* Actions rapides */}
      <div className="data-table-actions">
        <select 
          value={filterCategory} 
          onChange={(e) => setFilterCategory(e.target.value)}
          className="data-select"
        >
          <option value="">Toutes les catégories</option>
          {CATEGORIES.map(cat => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>

        <button 
          className="btn btn-secondary btn-small" 
          onClick={() => refetch()}
          disabled={loading}
        >
          🔄 Rafraîchir
        </button>

        {canEdit && (
          <>
            <button 
              className="btn btn-primary btn-small" 
              onClick={() => setShowAddForm(!showAddForm)}
              disabled={actionLoading}
            >
              ➕ Ajouter
            </button>
            
            <button 
              className="btn btn-secondary btn-small" 
              onClick={handleSeed}
              disabled={actionLoading}
              title="Créer des données de test initiales"
            >
              🌱 Initialiser
            </button>
          </>
        )}
      </div>

      {/* Erreur */}
      {(error || mutationError) && (
        <div className="data-error">
          ❌ {error || mutationError}
        </div>
      )}

      {/* Formulaire d'ajout */}
      {showAddForm && canEdit && (
        <form className="data-form" onSubmit={handleCreate}>
          <div className="data-form-row">
            <input
              type="text"
              placeholder="Nom *"
              value={newForm.name}
              onChange={(e) => setNewForm({ ...newForm, name: e.target.value })}
              required
              className="data-input"
            />
            <input
              type="text"
              placeholder="Valeur"
              value={newForm.value}
              onChange={(e) => setNewForm({ ...newForm, value: e.target.value })}
              className="data-input"
            />
            <select
              value={newForm.category}
              onChange={(e) => setNewForm({ ...newForm, category: e.target.value })}
              className="data-select"
            >
              {CATEGORIES.map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
            <button type="submit" className="btn btn-primary btn-small" disabled={actionLoading}>
              ✓
            </button>
            <button 
              type="button" 
              className="btn btn-secondary btn-small" 
              onClick={() => setShowAddForm(false)}
            >
              ✗
            </button>
          </div>
        </form>
      )}

      {/* Table des données */}
      {loading ? (
        <div className="data-loading">Chargement...</div>
      ) : data.length === 0 ? (
        <div className="data-empty">
          <p>Aucune donnée de test.</p>
          {canEdit && (
            <p>
              <button className="btn btn-primary" onClick={handleSeed}>
                🌱 Initialiser des données de test
              </button>
            </p>
          )}
        </div>
      ) : (
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Nom</th>
                <th>Valeur</th>
                <th>Catégorie</th>
                <th>Modifié par</th>
                <th>Dernière modification</th>
                {canEdit && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {data.map(item => (
                <tr key={item.id}>
                  <td className="data-id">{item.id}</td>
                  
                  {editingId === item.id ? (
                    // Mode édition
                    <>
                      <td>
                        <input
                          type="text"
                          value={editForm.name}
                          onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                          className="data-input"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={editForm.value}
                          onChange={(e) => setEditForm({ ...editForm, value: e.target.value })}
                          className="data-input"
                        />
                      </td>
                      <td>
                        <select
                          value={editForm.category}
                          onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                          className="data-select"
                        >
                          {CATEGORIES.map(cat => (
                            <option key={cat} value={cat}>{cat}</option>
                          ))}
                        </select>
                      </td>
                      <td>{item.last_modified_by}</td>
                      <td>{formatDate(item.updated_at)}</td>
                      <td className="data-actions">
                        <button 
                          className="btn btn-primary btn-small" 
                          onClick={() => handleUpdate(item.id)}
                          disabled={actionLoading}
                        >
                          ✓
                        </button>
                        <button 
                          className="btn btn-secondary btn-small" 
                          onClick={cancelEdit}
                        >
                          ✗
                        </button>
                      </td>
                    </>
                  ) : (
                    // Mode lecture
                    <>
                      <td className="data-name">{item.name}</td>
                      <td className="data-value">{item.value || <em>-</em>}</td>
                      <td>
                        <span className={`category-badge category-${item.category}`}>
                          {item.category}
                        </span>
                      </td>
                      <td className="data-user">{item.last_modified_by}</td>
                      <td className="data-date">{formatDate(item.updated_at)}</td>
                      {canEdit && (
                        <td className="data-actions">
                          <button 
                            className="btn btn-secondary btn-small" 
                            onClick={() => startEdit(item)}
                            disabled={actionLoading}
                          >
                            ✏️
                          </button>
                          <button 
                            className="btn btn-danger btn-small" 
                            onClick={() => handleDelete(item.id)}
                            disabled={actionLoading}
                          >
                            🗑️
                          </button>
                        </td>
                      )}
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Info statistiques */}
      <div className="data-stats">
        <span>Total: {data.length} entrée(s)</span>
        {data.length > 0 && (
          <span>
            Catégories: {[...new Set(data.map(d => d.category))].join(', ')}
          </span>
        )}
      </div>
    </div>
  )
}

export default DataTable
