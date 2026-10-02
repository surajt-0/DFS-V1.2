import { Link } from 'react-router-dom'
import { useState } from 'react'
import { Chip, ExportButtons, fmtTime, usePagedList } from './common'

const CATS = [
  ['session', 'Tabs & sessions', 'Open tabs with their back/forward history; Firefox also keeps recently closed tabs and windows.'],
  ['bookmark', 'Bookmarks', 'Current bookmarks and backups. A backup can still hold bookmarks the user deleted since.'],
  ['extension', 'Extensions', 'Installed extensions with install times and declared permissions.'],
  ['preference', 'Preferences', 'Home page, startup pages, download folder, signed-in account, proxy and DNS-over-HTTPS settings.'],
  ['network', 'Network state', 'Hosts the browser connected to, including ones absent from History.'],
]
const STATUS = {
  present: null,
  recovered_closed: ['warn', 'Recovered: closed tab/window'],
  backup_only: ['warn', 'Only in a backup (deleted since)'],
  prior_navigation: ['neutral', 'Earlier page in tab history'],
}

export default function SystemTab({ caseId, summary, setSuccess, setError }) {
  const [f, setF] = useState({ category: 'session', q: '', status: '' })
  const { data, pager } = usePagedList(caseId, 'state', f)
  const c = summary.counts.state
  const total = Object.values(c.by_category).reduce((a, b) => a + b, 0)
  const cat = CATS.find(([k]) => k === f.category)

  return (
    <>
      <p className="page-sub">
        Browser state that lives outside the main databases — and often survives after someone clears their history.
        Upload these files (or tick “Also collect browser system data” when scanning this computer).
      </p>

      {(c.recovered_closed > 0 || c.backup_only > 0) && (
        <div className="stat-grid" style={{ marginTop: 16 }}>
          <div className="stat-card"><div className="stat-value">{c.recovered_closed}</div><div className="stat-label">Recovered closed tabs</div></div>
          <div className="stat-card"><div className="stat-value">{c.backup_only}</div><div className="stat-label">Bookmarks only in backups</div></div>
        </div>
      )}

      <div className="chip-tabs">
        {CATS.map(([k, label]) => (
          <button key={k} className={`chip-tab ${f.category === k ? 'active' : ''}`} onClick={() => setF((p) => ({ ...p, category: k, status: '' }))}>
            {label} <span className="count">{c.by_category[k] || 0}</span>
          </button>
        ))}
      </div>
      <p className="muted" style={{ marginTop: 8 }}>{cat?.[2]}</p>

      {total === 0 ? (
        <div className="empty-state">
          <h3>No browser system data yet</h3>
          <p>
            Upload session files (<code>Current Session</code>, <code>Session_*</code>, <code>recovery.jsonlz4</code>),
            <code> Bookmarks</code>, <code>Preferences</code>, <code>extensions.json</code> or
            <code> Network Persistent State</code>.
          </p>
          <Link className="btn btn-primary" to={`/cases/${caseId}/upload`}>Upload evidence</Link>
        </div>
      ) : (
        <>
          <div className="toolbar">
            <input type="search" placeholder="Search…" value={f.q} onChange={(e) => setF((p) => ({ ...p, q: e.target.value }))} />
            <select value={f.status} onChange={(e) => setF((p) => ({ ...p, status: e.target.value }))}>
              <option value="">Any status</option>
              <option value="recovered_closed">Recovered closed tab</option>
              <option value="backup_only">Only in backup</option>
              <option value="prior_navigation">Earlier tab history</option>
              <option value="present">Present</option>
            </select>
            <div className="spacer" />
            <ExportButtons caseId={caseId} which="state" params={f} fileAccess={summary.file_access} onDone={setSuccess} onError={setError} />
          </div>
          {!data ? <div className="loading">Loading…</div> : data.results.length === 0 ? (
            <div className="empty-state"><h3>Nothing in this category</h3></div>
          ) : (
            <>
              <table className="table">
                <thead><tr><th>Browser</th><th>Item</th><th>Detail</th><th>Time</th><th>Status</th><th>Source file</th></tr></thead>
                <tbody>
                  {data.results.map((r) => {
                    const st = STATUS[r.status]
                    return (
                      <tr key={r.id}>
                        <td>{r.browser}</td>
                        <td className="wrap">{r.name}</td>
                        <td className="wrap muted">
                          {r.value || '—'}
                          {r.category === 'extension' && r.detail?.permissions?.length > 0 && (
                            <div>permissions: {r.detail.permissions.join(', ')}</div>
                          )}
                          {r.category === 'bookmark' && r.detail?.folder && <div>folder: {r.detail.folder}</div>}
                        </td>
                        <td className="nowrap">{fmtTime(r.timestamp)}</td>
                        <td>{st ? <Chip kind={st[0]}>{st[1]}</Chip> : <span className="muted">present</span>}</td>
                        <td className="wrap muted">{r.source_file}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {pager}
            </>
          )}
        </>
      )}
    </>
  )
}
