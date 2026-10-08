import { useAuth } from '../context/AuthContext'

function LoginPrompt() {
  const { login } = useAuth()

  return (
    <div className="hub-panel hub-panel--padded login-prompt">
      <h2>Bienvenue !</h2>
      <p>Connectez-vous via le Hub pour tester les différents niveaux d'accès.</p>
      <button className="hub-button" onClick={login}>
        Se connecter via le Hub
      </button>
    </div>
  )
}

export default LoginPrompt
