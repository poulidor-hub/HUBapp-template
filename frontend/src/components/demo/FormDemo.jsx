import React from 'react'
import { useForm } from '@tanstack/react-form'

export default function FormDemo() {
  const form = useForm({
    defaultValues: {
      name: '',
      email: '',
      siret: '',
      plan: 'standard',
    },
    onSubmit: async ({ value }) => {
      const res = await fetch('/api/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(value),
      })
      const data = await res.json()
      console.log('[FormDemo] Submit result:', data)
      alert(`Client créé (mock) : ${JSON.stringify(data)}`)
    },
  })

  return (
    <div className="card">
      <h2>Nouveau client (démo)</h2>
      <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>
        Formulaire TanStack Form avec validation. Les devtools montrent l'état en temps réel.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          form.handleSubmit()
        }}
        style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}
      >
        <form.Field
          name="name"
          validators={{
            onChange: ({ value }) =>
              value.length < 2 ? 'Le nom doit faire au moins 2 caractères' : undefined,
          }}
        >
          {(field) => (
            <div>
              <label htmlFor={field.name}>Nom du client</label>
              <input
                id={field.name}
                value={field.state.value}
                onBlur={field.handleBlur}
                onChange={(e) => field.handleChange(e.target.value)}
                style={{ display: 'block', width: '100%', marginTop: '0.25rem' }}
              />
              {field.state.meta.errors.length > 0 && (
                <span style={{ color: 'var(--color-danger)', fontSize: '0.8rem' }}>
                  {field.state.meta.errors[0]}
                </span>
              )}
            </div>
          )}
        </form.Field>

        <form.Field
          name="email"
          validators={{
            onChange: ({ value }) =>
              !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) && value.length > 0
                ? 'Email invalide'
                : undefined,
          }}
        >
          {(field) => (
            <div>
              <label htmlFor={field.name}>Email</label>
              <input
                id={field.name}
                type="email"
                value={field.state.value}
                onBlur={field.handleBlur}
                onChange={(e) => field.handleChange(e.target.value)}
                style={{ display: 'block', width: '100%', marginTop: '0.25rem' }}
              />
              {field.state.meta.errors.length > 0 && (
                <span style={{ color: 'var(--color-danger)', fontSize: '0.8rem' }}>
                  {field.state.meta.errors[0]}
                </span>
              )}
            </div>
          )}
        </form.Field>

        <form.Field
          name="siret"
          validators={{
            onChange: ({ value }) =>
              value.length > 0 && value.length !== 14
                ? `14 chiffres requis (actuel: ${value.length})`
                : undefined,
          }}
        >
          {(field) => (
            <div>
              <label htmlFor={field.name}>SIRET</label>
              <input
                id={field.name}
                value={field.state.value}
                onBlur={field.handleBlur}
                onChange={(e) => field.handleChange(e.target.value)}
                placeholder="12345678901234"
                style={{ display: 'block', width: '100%', marginTop: '0.25rem' }}
              />
              {field.state.meta.errors.length > 0 && (
                <span style={{ color: 'var(--color-danger)', fontSize: '0.8rem' }}>
                  {field.state.meta.errors[0]}
                </span>
              )}
            </div>
          )}
        </form.Field>

        <form.Field name="plan">
          {(field) => (
            <div>
              <label htmlFor={field.name}>Type de compte</label>
              <select
                id={field.name}
                value={field.state.value}
                onChange={(e) => field.handleChange(e.target.value)}
                style={{ display: 'block', width: '100%', marginTop: '0.25rem' }}
              >
                <option value="standard">Standard</option>
                <option value="premium">Premium</option>
              </select>
            </div>
          )}
        </form.Field>

        <form.Subscribe>
          {(state) => (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <button
                type="submit"
                disabled={!state.canSubmit || state.isSubmitting}
                style={{
                  padding: '0.5rem 1.5rem',
                  cursor: state.canSubmit ? 'pointer' : 'not-allowed',
                  opacity: state.canSubmit ? 1 : 0.5,
                }}
              >
                {state.isSubmitting ? 'Envoi...' : 'Enregistrer'}
              </button>
              <button
                type="button"
                onClick={() => form.reset()}
                style={{ padding: '0.5rem 1rem' }}
              >
                Réinitialiser
              </button>
              {!state.isValid && (
                <span style={{ color: 'var(--color-danger)', fontSize: '0.8rem' }}>
                  {Object.keys(state.fieldErrors).length} erreur(s)
                </span>
              )}
            </div>
          )}
        </form.Subscribe>
      </form>
    </div>
  )
}
