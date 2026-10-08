import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useAuth } from '../context/AuthContext'
import LoginPrompt from '../components/LoginPrompt'
import PageHeader from '../components/PageHeader'
import ExampleList from '../components/ExampleList'

export default function HomePage() {
  const { isAuthenticated } = useAuth()
  // Total remonté par ExampleList (même requête ['items', page]) pour la meta.
  const [total, setTotal] = useState(null)

  if (!isAuthenticated) {
    return <LoginPrompt />
  }

  return (
    <>
      <PageHeader
        title="Accueil"
        meta={total != null ? `${total} éléments · structure canonique` : 'structure canonique'}
        actions={(
          <Link to="/demo/form" className="hub-button">
            Démo Form
          </Link>
        )}
      />
      <ExampleList onTotal={setTotal} />
    </>
  )
}
