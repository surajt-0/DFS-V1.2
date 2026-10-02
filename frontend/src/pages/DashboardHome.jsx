import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { dashboardApi, evidenceApi } from '../api/client'
import { useAuth } from '../api/AuthContext'
import Banner from '../components/Banner'
import Badge from '../components/Badge'
import UsageBar from '../components/UsageBar'
import PlanLimitNotice from '../components/PlanLimitNotice'
import agamyaLogo from '../assets/agamya-logo.jpg'

const fmtDate = (d) =>
  d ? new Date(d).toLocaleString('en-IN', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

export default function DashboardHome() {
  const { me } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [demoBusy, setDemoBusy] = useState(false)

  function load() {
    dashboardApi.stats().then(setData).catch((e) => setError(e.message))
  }
  useEffect(load, [])

  async function createDemoCase() {
    setDemoBusy(true)
    setError('')
    try {
      const caseObj = await evidenceApi.createDemoCase()
      window.location.href = `/cases/${caseObj.id}`
    } catch (e) {
      setError(e.message)
    } finally {
      setDemoBusy(false)
    }
  }

  if (!data && !error) return <div className="page loading">Loading dashboard…</div>

  const isReadOnly = me?.organization?.plan?.is_read_only
  const canCreate = !me?.is_viewer

  return (
    <div className="page">
      <div className="page-head page-head-branded">
        <img src={agamyaLogo} alt="Agamya Cyber Tech" className="page-head-logo" />
        <div>
          <h1>Dashboard</h1>
          <p className="page-sub">{me?.organization?.name}</p>
        </div>
      </div>

      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>

      {data && (
        <>
          <div className="stat-grid">
            <div className="stat-card">
              <div className="stat-value">{data.stats.total_cases}</div>
              <div className="stat-label">Total cases</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{data.stats.open_cases}</div>
              <div className="stat-label">Open</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{data.stats.closed_cases}</div>
              <div className="stat-label">Closed</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{data.stats.total_evidence}</div>
              <div className="stat-label">Evidence files</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{data.stats.parsed_evidence}</div>
              <div className="stat-label">Parsed</div>
            </div>
          </div>

          <div className="toolbar">
            <Link className="btn btn-primary" to="/cases/new" style={{ pointerEvents: canCreate ? 'auto' : 'none', opacity: canCreate ? 1 : 0.5 }}>
              + New case
            </Link>
            <button className="btn btn-ghost" disabled={demoBusy || !canCreate} onClick={createDemoCase}>
              {demoBusy ? 'Creating demo…' : 'Load demo case'}
            </button>
          </div>
          {isReadOnly && (
            <PlanLimitNotice>The Free plan is view-only — upgrade to create or edit cases.</PlanLimitNotice>
          )}

          <div className="home-grid">
            <div className="card">
              <div className="card-title">Recent cases</div>
              {data.recent_cases.length === 0 ? (
                <p className="muted">No cases yet.</p>
              ) : (
                <div className="evidence-list">
                  {data.recent_cases.map((c) => (
                    <Link key={c.id} className="evidence-row" to={`/cases/${c.id}`}>
                      <div className="evidence-row-main">
                        <span className="evidence-row-name">{c.name}</span>
                        <span className="evidence-row-meta">
                          {c.case_number} · {c.evidence_count} evidence file{c.evidence_count === 1 ? '' : 's'}
                        </span>
                      </div>
                      <Badge kind={c.status} />
                    </Link>
                  ))}
                </div>
              )}
              <div style={{ marginTop: 14 }}>
                <Link className="btn btn-ghost btn-sm" to="/cases">
                  View all cases →
                </Link>
              </div>
            </div>

            <div className="card">
              <div className="card-title">Plan usage</div>
              <UsageBar label="Cases used" usage={data.case_usage} />

              <div className="card-title" style={{ marginTop: 20 }}>
                Evidence by type
              </div>
              {data.type_breakdown.length === 0 ? (
                <p className="muted">No evidence uploaded yet.</p>
              ) : (
                <ul className="type-breakdown">
                  {data.type_breakdown.map((t) => (
                    <li key={t.evidence_type}>
                      <span>{t.evidence_type.replaceAll('_', ' ')}</span>
                      <strong>{t.n}</strong>
                    </li>
                  ))}
                </ul>
              )}

              <div className="card-title" style={{ marginTop: 20 }}>
                Recent activity {data.activity_last_week > 0 && <span className="muted">({data.activity_last_week} in the last 7 days)</span>}
              </div>
              {data.recent_activity.length === 0 ? (
                <p className="muted">No activity yet.</p>
              ) : (
                <ul className="activity-list">
                  {data.recent_activity.map((a) => (
                    <li key={a.id}>
                      <span className="act-action">{a.action}</span>
                      <span className="act-meta">
                        {a.username} · {fmtDate(a.timestamp)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
