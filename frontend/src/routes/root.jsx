import React, { useState, useEffect } from 'react'
import { Outlet } from '@tanstack/react-router'
import { useConfig } from '../context/ConfigContext'
import Header from '../components/Header'
import MessageBanner from '../components/MessageBanner'
import MessageArchive from '../components/MessageArchive'

export function RootLayout() {
  const [theme, setTheme] = useState(() =>
    localStorage.getItem('theme') || 'light'
  )
  const config = useConfig()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark')
  }

  if (!config.loaded) {
    return (
      <div className="loading">
        <p>Chargement de la configuration...</p>
      </div>
    )
  }

  return (
    <div className="app">
      <Header theme={theme} toggleTheme={toggleTheme} />
      <div className="container">
        <Outlet />
      </div>
      {/* Messagerie Hub (SSE) — flottants, null si non authentifié */}
      <MessageBanner />
      <MessageArchive />
    </div>
  )
}
