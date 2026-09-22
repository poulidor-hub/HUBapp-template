import React, { useState } from 'react'
import { useForm } from '@tanstack/react-form'

export default function FormDemo() {
  const [submitResult, setSubmitResult] = useState(null)

  const form = useForm({
    defaultValues: {
      name: '',
      email: '',
      siret: '',
      plan: 'standard',
    },
    onSubmit: async ({ value }) => {
      // Cible /api/test-data (endpoint de démonstration du backend, activé
      // via ENABLE_DEMO_ENDPOINTS en dev) — contrat TestDataCreate :
      // {name, value?, category}. Voir backend/routes/test_data.py.
      const payload = {
        name: value.name,
        value: [
          value.email && `email: ${value.email}`,
          value.siret && `SIRET: ${value.siret}`,
        ]
          .filter(Boolean)
          .join(' — ') || null,
        category: value.plan,
      }
      const res = await fetch('/api/test-data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => null)
      console.log('[FormDemo] Submit result:', data)
      // Retour inline (pas d'alert()) — style .test-result du template
      setSubmitResult({
        ok: res.ok,
        message: res.ok
          ? `Donnée de test créée (id ${data?.id}) : ${JSON.stringify(data)}`
          : `Erreur (${res.status}) : ${data?.detail || 'requête refusée'}`,
      })
    },
  })

  return (
    <div className="card">
      <h2>Nouveau client (démo)</h2>
      <p className="card-intro">
        Formulaire TanStack Form avec validation. Les devtools montrent l'état en temps réel.
      </p>

      <form
        className="demo-form"
        onSubmit={(e) => {
          e.preventDefault()
          form.handleSubmit()
        }}
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
                className="data-input"
                value={field.state.value}
                onBlur={field.handleBlur}
                onChange={(e) => field.handleChange(e.target.value)}
              />
              {field.state.meta.errors.length > 0 && (
                <span className="demo-form-error">
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
                className="data-input"
                value={field.state.value}
                onBlur={field.handleBlur}
                onChange={(e) => field.handleChange(e.target.value)}
              />
              {field.state.meta.errors.length > 0 && (
                <span className="demo-form-error">
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
                className="data-input"
                value={field.state.value}
                onBlur={field.handleBlur}
                onChange={(e) => field.handleChange(e.target.value)}
                placeholder="12345678901234"
              />
              {field.state.meta.errors.length > 0 && (
                <span className="demo-form-error">
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
                className="data-select"
                value={field.state.value}
                onChange={(e) => field.handleChange(e.target.value)}
              >
                <option value="standard">Standard</option>
                <option value="premium">Premium</option>
              </select>
            </div>
          )}
        </form.Field>

        <form.Subscribe>
          {(state) => (
            <div className="demo-form-footer">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={!state.canSubmit || state.isSubmitting}
              >
                {state.isSubmitting ? 'Envoi...' : 'Enregistrer'}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  form.reset()
                  setSubmitResult(null)
                }}
              >
                Réinitialiser
              </button>
              {!state.isValid && (
                <span className="demo-form-error">
                  {Object.keys(state.fieldErrors).length} erreur(s)
                </span>
              )}
            </div>
          )}
        </form.Subscribe>

        {submitResult && (
          <div className={`test-result ${submitResult.ok ? 'success' : 'error'}`}>
            {submitResult.message}
          </div>
        )}
      </form>
    </div>
  )
}
