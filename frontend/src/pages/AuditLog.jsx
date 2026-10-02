import { useEffect, useState } from 'react'
import { auditApi } from '../api/client'
import Banner from '../components/Banner'
import Pagination from '../components/Pagination'
import PlanLimitNotice from '../components/PlanLimitNotice'

const fmtDate = (d) =>
  new Date(d).toLocaleString('en-IN', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

export default function AuditLog() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [action, setAction] = useState('')
  const [page, setPage] = useState(1)

  function load() {
    auditApi
      .list({ q, action, page })
      .then(setData)
      .catch((e) => setError(e.message))
  }
  useEffect(load, [q, action, page])

  return (
    <div className="page">
      <div className="page-head">
        <h1>Audit log</h1>
        <p className="page-sub">
          {data?.org_wide ? 'Every action across your organization.' : 'Your own actions.'}
        </p>
      </div>

      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>

      {data && !data.org_wide && !data.feature_audit_log && (
        <PlanLimitNotice>
          Organization-wide audit visibility isn't included on your current plan — showing your own activity only.
        </PlanLimitNotice>
      )}

      {!data ? (
        <div className="loading">Loading…</div>
      ) : (
        <>
          <div className="toolbar">
            <input
              type="search"
              placeholder="Search activity…"
              value={q}
              onChange={(e) => {
                setPage(1)
                setQ(e.target.value)
              }}
            />
            <select
              value={action}
              onChange={(e) => {
                setPage(1)
                setAction(e.target.value)
              }}
            >
              <option value="">All actions</option>
              {data.actions.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>

          {data.results.length === 0 ? (
            <div className="empty-state">
              <h3>No activity found</h3>
            </div>
          ) : (
            <>
              <table className="table" style={{ marginTop: 16 }}>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>User</th>
                    <th>Action</th>
                    <th>Detail</th>
                    <th>Case</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((entry) => (
                    <tr key={entry.id}>
                      <td>{fmtDate(entry.timestamp)}</td>
                      <td>{entry.username}</td>
                      <td>{entry.action}</td>
                      <td>{entry.detail}</td>
                      <td>{entry.case_number || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination count={data.count} pageSize={50} page={page} onChange={setPage} />
            </>
          )}
        </>
      )}
    </div>
  )
}
