import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { accountsApi } from '../api/client'
import { useAuth } from '../api/AuthContext'
import Banner from '../components/Banner'
import agamyaLogo from '../assets/agamya-logo.jpg'

const initialForm = {
  username: '', email: '', first_name: '', last_name: '',
  organization: '', badge_id: '', role: 'admin',
  password1: '', password2: '',
}

export default function Signup() {
  const navigate = useNavigate()
  const { refresh } = useAuth()
  const [form, setForm] = useState(initialForm)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await accountsApi.signup(form)
      await refresh()
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1>Create your account</h1>
        <p className="page-sub">
          You'll own a new organization on the Free plan — upgrade any time from Pricing.
        </p>
      </div>
      <div className="auth-card">
        <img src={agamyaLogo} alt="Agamya Cyber Tech" className="auth-logo" />
        <Banner kind="danger" onClose={() => setError('')}>
          {error}
        </Banner>
        <form onSubmit={onSubmit}>
          <div className="field-row">
            <div className="field">
              <label>Username</label>
              <input value={form.username} onChange={(e) => set('username', e.target.value)} required />
            </div>
            <div className="field">
              <label>Email</label>
              <input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} required />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>First name</label>
              <input value={form.first_name} onChange={(e) => set('first_name', e.target.value)} />
            </div>
            <div className="field">
              <label>Last name</label>
              <input value={form.last_name} onChange={(e) => set('last_name', e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label>Organization / company name</label>
            <input value={form.organization} onChange={(e) => set('organization', e.target.value)} required />
          </div>
          <div className="field-row">
            <div className="field">
              <label>Examiner / Badge ID</label>
              <input value={form.badge_id} onChange={(e) => set('badge_id', e.target.value)} />
            </div>
            <div className="field">
              <label>Role label</label>
              <select value={form.role} onChange={(e) => set('role', e.target.value)}>
                <option value="admin">Administrator</option>
                <option value="examiner">Forensic Examiner</option>
                <option value="viewer">Read-only Reviewer</option>
              </select>
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>Password</label>
              <input type="password" value={form.password1} onChange={(e) => set('password1', e.target.value)} required />
            </div>
            <div className="field">
              <label>Confirm password</label>
              <input type="password" value={form.password2} onChange={(e) => set('password2', e.target.value)} required />
            </div>
          </div>
          <button className="btn btn-primary btn-block" disabled={busy} type="submit">
            {busy ? 'Creating account…' : 'Create account'}
          </button>
        </form>
        <div className="auth-foot">
          Already have an account? <Link to="/login">Log in</Link>
        </div>
      </div>
    </div>
  )
}
