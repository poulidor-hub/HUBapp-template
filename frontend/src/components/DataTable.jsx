import React, { useState, useEffect, useCallback } from 'react'
import { useConfig } from '../context/ConfigContext'
import { useAuth } from '../context/AuthContext'

// Catégories disponibles
const CATEGORIES = ['general', 'infrastructure', 'stack', 'config', 'custom']

function DataTable() {
  const config = useConfig()
  const { token, isAuthenticated, userInfo } = useAuth()
  
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', value: '', category: 'general' })
  const [newForm, setNewForm] = useState({ name: '', value: '', category: 'general' })
  const [showAddForm, setShowAddForm] = useState(false)
  const [filterCategory, setFilterCategory] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  // Charger les données
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    
    try {
      const url = filterCategory 
        ? `${config.apiUrl}/api/test-data?category=${filterCategory}`
        : `${config.apiUrl}/api/test-data`
      
      const response = await fetch(url)
      
      if (!response.ok) {
        throw new Error(`Erreur ${response.status}`)
      }
      
      const result = await response.json()
      setData(result.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [config.apiUrl, filterCategory])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Créer une entrée
  const handleCreate = async (e) => {
    e.preventDefault()
    if (!token || !newForm.name.trim()) return
    
    setActionLoading(true)
    try {
      const response = await fetch(`${config.apiUrl}/api/test-data`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(newForm)
      })
      
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || `Erreur ${response.status}`)
      }
      
      setNewForm({ name: '', value: '', category: 'general' })
      setShowAddForm(false)
      await fetchData()
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  // Mettre à jour une entrée
  const handleUpdate = async (id) => {
    if (!token) return
    
    setActionLoading(true)
    try {
      const response = await fetch(`${config.apiUrl}/api/test-data/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(editForm)
      })
      
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || `Erreur ${response.status}`)
      }
      
      setEditingId(null)
      await fetchData()
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  // Supprimer une entrée
  const handleDelete = async (id) => {
    if (!token) return
    if (!confirm('Êtes-vous sûr de vouloir supprimer cette entrée ?')) return
    
    setActionLoading(true)
    try {
      const response = await fetch(`${config.apiUrl}/api/test-data/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || `Erreur ${response.status}`)
      }
      
      await fetchData()
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  // Initialiser des données de test
  const handleSeed = async () => {
    if (!token) return
    
    setActionLoading(true)
    try {
      const response = await fetch(`${config.apiUrl}/api/test-data/seed`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || `Erreur ${response.status}`)
      }
      
      await fetchData()
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
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
  const canEdit = isAuthenticated && userInfo?.app_role && 
    ['user', 'manager', 'admin'].includes(userInfo.app_role)

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
          onClick={fetchData}
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
      {error && (
        <div className="data-error">
          ❌ {error}
          <button onClick={() => setError(null)}>×</button>
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
