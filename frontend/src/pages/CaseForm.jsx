import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { casesApi } from '../api/client'
import { useAuth } from '../api/AuthContext'
import Banner from '../components/Banner'
import PlanLimitNotice from '../components/PlanLimitNotice'

const emptyForm = { name: '', description: '', priority: 'medium', status: 'open', subject_name: '', tags: '' }

export default function CaseForm() {
  const { id } = useParams()
  const isEdit = !!id
  const navigate = useNavigate()
  const { me } = useAuth()

  const [form, setForm] = useState(emptyForm)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(isEdit)

  useEffect(() => {
    if (!isEdit) return
    casesApi
      .detail(id)
      .then((c) =>
        setForm({
          name: c.name, description: c.description || '', priority: c.priority,
          status: c.status, subject_name: c.subject_name || '', tags: c.tags || '',
        })
      )
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id, isEdit])

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (isEdit) {
        await casesApi.update(id, form)
        navigate(`/cases/${id}`)
      } else {
        const created = await casesApi.create(form)
        navigate(`/cases/${created.id}`)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const org = me?.organization

  if (loading) return <div className="page loading">Loading case…</div>

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1>{isEdit ? 'Edit case' : 'New case'}</h1>
      </div>

      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>

      {!isEdit && org?.plan?.is_read_only && (
        <PlanLimitNotice>The Free plan is view-only — upgrade to create cases.</PlanLimitNotice>
      )}

      <form className="auth-card" onSubmit={onSubmit}>
        <div className="field">
          <label>Case name</label>
          <input value={form.name} onChange={(e) => set('name', e.target.value)} required autoFocus />
        </div>
        <div className="field">
          <label>Description</label>
          <textarea value={form.description} onChange={(e) => set('description', e.target.value)} />
        </div>
        <div className="field-row">
          <div className="field">
            <label>Priority</label>
            <select value={form.priority} onChange={(e) => set('priority', e.target.value)}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          {isEdit && (
            <div className="field">
              <label>Status</label>
              <select value={form.status} onChange={(e) => set('status', e.target.value)}>
                <option value="open">Open</option>
                <option value="closed">Closed</option>
                <option value="archived">Archived</option>
              </select>
            </div>
          )}
        </div>
        <div className="field">
          <label>Subject / custodian</label>
          <input value={form.subject_name} onChange={(e) => set('subject_name', e.target.value)} />
        </div>
        <div className="field">
          <label>Tags (comma-separated)</label>
          <input value={form.tags} onChange={(e) => set('tags', e.target.value)} />
        </div>
        <div className="form-actions">
          <button className="btn btn-primary" disabled={busy} type="submit">
            {busy ? 'Saving…' : isEdit ? 'Save changes' : 'Create case'}
          </button>
          <button className="btn btn-ghost" type="button" onClick={() => navigate(-1)}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}
