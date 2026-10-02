import { useEffect, useState } from 'react'
import { accountsApi } from '../api/client'
import Banner from '../components/Banner'

export default function Profile() {
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)

  const [pw, setPw] = useState({ old_password: '', new_password1: '', new_password2: '' })
  const [pwError, setPwError] = useState('')
  const [pwSuccess, setPwSuccess] = useState('')
  const [pwBusy, setPwBusy] = useState(false)

  useEffect(() => {
    accountsApi.profile().then(setProfile).catch((e) => setError(e.message))
  }, [])

  function set(field, value) {
    setProfile((p) => ({ ...p, [field]: value }))
  }

  async function onSave(e) {
    e.preventDefault()
    setError('')
    setSuccess('')
    setBusy(true)
    try {
      const updated = await accountsApi.updateProfile({
        email: profile.email, first_name: profile.first_name,
        last_name: profile.last_name, badge_id: profile.badge_id,
      })
      setProfile(updated)
      setSuccess('Profile updated.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function onChangePassword(e) {
    e.preventDefault()
    setPwError('')
    setPwSuccess('')
    setPwBusy(true)
    try {
      await accountsApi.changePassword(pw)
      setPwSuccess('Password changed.')
      setPw({ old_password: '', new_password1: '', new_password2: '' })
    } catch (err) {
      setPwError(err.message)
    } finally {
      setPwBusy(false)
    }
  }

  if (!profile) return <div className="page loading">Loading profile…</div>

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1>Profile</h1>
        <p className="page-sub">
          {profile.organization} <span className="role-pill">{profile.role}</span>
        </p>
      </div>

      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>
      <Banner kind="success" onClose={() => setSuccess('')}>
        {success}
      </Banner>

      <form className="auth-card" onSubmit={onSave}>
        <div className="field">
          <label>Username</label>
          <input value={profile.username} disabled />
        </div>
        <div className="field-row">
          <div className="field">
            <label>First name</label>
            <input value={profile.first_name || ''} onChange={(e) => set('first_name', e.target.value)} />
          </div>
          <div className="field">
            <label>Last name</label>
            <input value={profile.last_name || ''} onChange={(e) => set('last_name', e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label>Email</label>
          <input type="email" value={profile.email || ''} onChange={(e) => set('email', e.target.value)} />
        </div>
        <div className="field">
          <label>Badge / examiner ID</label>
          <input value={profile.badge_id || ''} onChange={(e) => set('badge_id', e.target.value)} />
        </div>
        <div className="form-actions">
          <button className="btn btn-primary" disabled={busy} type="submit">
            {busy ? 'Saving…' : 'Save profile'}
          </button>
        </div>
      </form>

      <div className="page-head" style={{ marginTop: 32 }}>
        <h2>Change password</h2>
      </div>
      <Banner kind="danger" onClose={() => setPwError('')}>
        {pwError}
      </Banner>
      <Banner kind="success" onClose={() => setPwSuccess('')}>
        {pwSuccess}
      </Banner>
      <form className="auth-card" onSubmit={onChangePassword}>
        <div className="field">
          <label>Current password</label>
          <input
            type="password"
            value={pw.old_password}
            onChange={(e) => setPw((p) => ({ ...p, old_password: e.target.value }))}
            required
          />
        </div>
        <div className="field-row">
          <div className="field">
            <label>New password</label>
            <input
              type="password"
              value={pw.new_password1}
              onChange={(e) => setPw((p) => ({ ...p, new_password1: e.target.value }))}
              required
            />
          </div>
          <div className="field">
            <label>Confirm new password</label>
            <input
              type="password"
              value={pw.new_password2}
              onChange={(e) => setPw((p) => ({ ...p, new_password2: e.target.value }))}
              required
            />
          </div>
        </div>
        <div className="form-actions">
          <button className="btn btn-primary" disabled={pwBusy} type="submit">
            {pwBusy ? 'Updating…' : 'Change password'}
          </button>
        </div>
      </form>
    </div>
  )
}
