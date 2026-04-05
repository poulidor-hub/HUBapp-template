import React, { useState, useEffect } from 'react'
import { useConfig } from './context/ConfigContext'
import { useAuth } from './context/AuthContext'
import Header from './components/Header'
import UserCard from './components/UserCard'
import TokenCard from './components/TokenCard'
import EndpointTests from './components/EndpointTests'
import M2MTests from './components/M2MTests'
import LoginPrompt from './components/LoginPrompt'
import DataTable from './components/DataTable'
import MessageBanner from './components/MessageBanner'
import MessageArchive from './components/MessageArchive'

function App() {
  const [theme, setTheme] = useState(() => 
    localStorage.getItem('theme') || 'light'
  )
  const [loadTimeout, setLoadTimeout] = useState(false)
  const config = useConfig()
  const { isAuthenticated } = useAuth()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    if (config.loaded) return
    const timer = setTimeout(() => setLoadTimeout(true), 10000)
    return () => clearTimeout(timer)
  }, [config.loaded])

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark')
  }

  if (!config.loaded) {
    return (
      <div className="loading">
        {loadTimeout ? (
          <>
            <p>La configuration n'a pas pu être chargée.</p>
            <button
              onClick={() => window.location.reload()}
              style={{ marginTop: '1rem', padding: '0.5rem 1rem', cursor: 'pointer' }}
            >
              Réessayer
            </button>
          </>
        ) : (
          <p>Chargement de la configuration...</p>
        )}
      </div>
    )
  }

  return (
    <div className="app">
      <Header theme={theme} toggleTheme={toggleTheme} />
      
      <div className="container">
        {!isAuthenticated ? (
          <LoginPrompt />
        ) : (
          <>
            <UserCard />
            <TokenCard />
          </>
        )}
        
        {/* Tableau de données de test pour backup */}
        <DataTable />
        
        <EndpointTests />
        
        {/* Tests M2M - visible uniquement pour les admins authentifiés */}
        {isAuthenticated && <M2MTests />}
      </div>

      {/* Overlays flottants — indépendants du layout */}
      <MessageBanner />
      <MessageArchive />
    </div>
  )
}

export default App
