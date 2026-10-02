import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { accountsApi } from '../api/client'
import { useAuth } from '../api/AuthContext'
import Banner from '../components/Banner'
import agamyaLogo from '../assets/agamya-logo.jpg'

export default function Login() {
  const navigate = useNavigate()
  const { refresh } = useAuth()
  const [params] = useSearchParams()
  const next = params.get('next') || '/dashboard'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await accountsApi.login(username, password)
      await refresh()
      navigate(next, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1>Log in</h1>
        <p className="page-sub">Access your organization's cases and evidence.</p>
      </div>
      <div className="auth-card">
        <img src={agamyaLogo} alt="Agamya Cyber Tech" className="auth-logo" />
        <Banner kind="danger" onClose={() => setError('')}>
          {error}
        </Banner>
        <form onSubmit={onSubmit}>
          <div className="field">
            <label>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div className="field">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button className="btn btn-primary btn-block" disabled={busy} type="submit">
            {busy ? 'Logging in…' : 'Log in'}
          </button>
        </form>
        <div className="auth-foot">
          Don't have an account? <Link to="/signup">Create one</Link>
        </div>
      </div>
    </div>
  )
}
