import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import Banner from '../components/Banner'
import FileAccessBadges from '../components/FileAccessBadges'

const fmtINR = (n) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n)
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' }) : '—')

export default function Dashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function load() {
    api
      .mySubscription()
      .then(setData)
      .catch((e) => setError(e.message))
  }

  useEffect(load, [])

  async function handleCancel() {
    if (!window.confirm('Cancel your subscription and move to the Free plan?')) return
    setBusy(true)
    setError('')
    try {
      await api.cancelSubscription()
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (error) {
    return (
      <div className="page">
        <Banner kind="danger">{error}</Banner>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page">
        <div className="loading">Loading your subscription…</div>
      </div>
    )
  }

  const { organization, case_usage, is_owner, payments } = data
  const plan = organization.plan
  const sub = organization.subscription

  return (
    <div className="page">
      <div className="page-head">
        <h1>My Subscription</h1>
        <p className="page-sub">{organization.name}</p>
      </div>

      <div className="dash-grid">
        <div className="card">
          <div className="card-title">Current plan</div>
          <div className="dash-plan-name">{plan.name}</div>
          <div className="muted">{plan.tagline}</div>

          <div className="usage-bar">
            <div className="usage-label">
              <span>Cases used</span>
              <span>
                {case_usage.used} {case_usage.unlimited ? '' : `/ ${case_usage.limit}`}
              </span>
            </div>
            {!case_usage.unlimited && (
              <div className="usage-track">
                <div
                  className="usage-fill"
                  style={{ width: `${Math.min(100, (case_usage.used / Math.max(case_usage.limit, 1)) * 100)}%` }}
                />
              </div>
            )}
          </div>

          {sub && (
            <div className="dash-sub-meta">
              <div>
                Billing cycle: <strong>{sub.billing_cycle}</strong>
              </div>
              <div>
                Status: <strong>{sub.status}</strong>
              </div>
              <div>
                Renews: <strong>{fmtDate(sub.current_period_end)}</strong>
              </div>
            </div>
          )}

          <FileAccessBadges fileAccess={plan.file_access} />

          {is_owner && (
            <div className="dash-actions">
              <Link className="btn btn-primary" to="/pricing">
                Change plan
              </Link>
              {!plan.is_free && (
                <button className="btn btn-danger-ghost" disabled={busy} onClick={handleCancel}>
                  Cancel subscription
                </button>
              )}
            </div>
          )}
          {!is_owner && <p className="muted">Only the organization owner can change billing.</p>}
        </div>

        <div className="card">
          <div className="card-title">Payment history</div>
          {payments.length === 0 ? (
            <p className="muted">No payments yet.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Plan</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td>{p.invoice_number}</td>
                    <td>
                      {p.plan_name} ({p.billing_cycle})
                    </td>
                    <td>{fmtINR(p.amount_inr)}</td>
                    <td>
                      <span className={`status-pill status-${p.status}`}>{p.status}</span>
                      {p.is_demo && <span className="demo-pill">demo</span>}
                    </td>
                    <td>{fmtDate(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
