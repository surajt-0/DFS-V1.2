import { useState } from 'react'
import { Link } from 'react-router-dom'
import { recoveryApi } from '../../api/client'
import Banner from '../../components/Banner'
import { Chip, Conf, ExportButtons, fmtTime, usePagedList } from './common'

const SOURCE_LABEL = {
  freelist_page: 'Freed page',
  freeblock: 'Freeblock / gap',
  wal: 'WAL',
  wal_stale: 'Stale WAL frame',
}
const STATUS_LABEL = { deleted: 'Deleted', older_version: 'Older version', wal_only: 'Only in WAL' }
const KIND_LABEL = { history: 'History', download: 'Download', cookie: 'Cookie', login: 'Login' }

function RunCard({ ev, canRun, running, onRun }) {
  const r = ev.last_run
  return (
    <div className="run-card">
      <div className="run-card-head">
        <div>
          <strong>{ev.original_filename}</strong>
          <div className="muted">{ev.evidence_type_display}</div>
        </div>
        <button className="btn btn-primary btn-sm" disabled={!canRun || running} onClick={() => onRun(ev.id)}>
          {running ? 'Recovering…' : r ? 'Run again' : 'Recover deleted data'}
        </button>
      </div>
      <div className="run-card-meta">
        <Chip kind={ev.has_wal ? 'ok' : 'neutral'} title="Write-ahead log: holds the newest (and some deleted) rows">
          {ev.has_wal ? 'WAL file captured' : 'No WAL file'}
        </Chip>
        {ev.snapshot_copy && (
          <Chip kind="warn" title="Collected with SQLite's snapshot fallback, which only contains live rows">
            Snapshot copy
          </Chip>
        )}
        {r && (
          <>
            <Chip kind={r.status === 'failed' ? 'danger' : r.status === 'partial' ? 'warn' : 'ok'}>
              {r.status === 'failed' ? 'Failed' : `${r.records_found} recovered`}
            </Chip>
            <span className="muted">last run {fmtTime(r.created_at)}</span>
          </>
        )}
      </div>
      {r?.error && <div className="run-note run-note-danger">{r.error}</div>}
      {r?.warnings?.map((w) => (
        <div key={w} className="run-note">
          {w}
        </div>
      ))}
    </div>
  )
}

export default function DeletedTab({ caseId, summary, reloadSummary, setSuccess, setError }) {
  const [running, setRunning] = useState(null) // evidence id | 'all'
  const [tick, setTick] = useState(0)
  const [f, setF] = useState({ q: '', kind: '', confidence: '', source: '', status: '', evidence: '', sort: '-event_time' })
  const { data, error, pager } = usePagedList(caseId, 'deleted', f, true, tick)
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }))

  async function run(evidenceId) {
    setRunning(evidenceId || 'all')
    setError('')
    setSuccess('')
    try {
      const res = await recoveryApi.carve(caseId, evidenceId)
      const total = res.results.reduce((n, r) => n + r.records_found, 0)
      const failed = res.results.filter((r) => r.status === 'failed').length
      setSuccess(
        `Recovery finished: ${total} record(s) found across ${res.results.length} file(s)` +
          (failed ? `, ${failed} could not be processed (see details below).` : '.')
      )
      await reloadSummary()
      setTick((t) => t + 1)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(null)
    }
  }

  const ev = summary.carvable_evidence
  const counts = summary.counts.deleted

  return (
    <>
      <p className="page-sub">
        Finds records a user deleted from a browser database but that SQLite hasn't overwritten yet — in freed pages,
        the gaps inside live pages, and the write-ahead log. Nothing is changed in your evidence: recovery runs on a
        temporary copy.
      </p>

      {error && <Banner kind="danger">{error}</Banner>}

      {ev.length === 0 ? (
        <div className="empty-state">
          <h3>No browser databases in this case</h3>
          <p>
            Upload a History, Cookies, Login Data, places.sqlite or cookies.sqlite file first
            (plus its <code>-wal</code> file if you have one).
          </p>
          <Link className="btn btn-primary" to={`/cases/${caseId}/upload`}>
            Upload evidence
          </Link>
        </div>
      ) : (
        <>
          <div className="run-list">
            {ev.map((e) => (
              <RunCard key={e.id} ev={e} canRun={summary.can_run && running === null} running={running === e.id || running === 'all'} onRun={run} />
            ))}
          </div>
          <div style={{ marginTop: 12 }}>
            {ev.length > 1 && (
              <button className="btn btn-ghost btn-sm" disabled={!summary.can_run || running !== null} onClick={() => run(null)}>
                {running === 'all' ? 'Recovering…' : 'Run on all files'}
              </button>
            )}
            {!summary.can_run && (
              <span className="muted" style={{ marginLeft: 10 }}>
                {summary.read_only_plan ? 'Your plan is view-only.' : "You don't have permission to run recovery on this case."}
              </span>
            )}
          </div>
        </>
      )}

      {counts.total > 0 && (
        <div className="stat-grid">
          <div className="stat-card">
            <div className="stat-value">{counts.total}</div>
            <div className="stat-label">Recovered records</div>
          </div>
          {['high', 'medium', 'low'].map((c) => (
            <div className="stat-card" key={c}>
              <div className="stat-value">{counts.by_confidence[c] || 0}</div>
              <div className="stat-label">{c} confidence</div>
            </div>
          ))}
          <div className="stat-card">
            <div className="stat-value">{counts.by_status.older_version || 0}</div>
            <div className="stat-label">Older versions of live rows</div>
          </div>
        </div>
      )}

      {counts.total > 0 && data && (
        <>
          <div className="toolbar">
            <input type="search" placeholder="Search URL, path, host, title…" value={f.q} onChange={set('q')} />
            <select value={f.kind} onChange={set('kind')}>
              <option value="">All types</option>
              {Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <select value={f.confidence} onChange={set('confidence')}>
              <option value="">Any confidence</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <select value={f.status} onChange={set('status')}>
              <option value="">Any status</option>
              {Object.entries(STATUS_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <select value={f.source} onChange={set('source')}>
              <option value="">Found anywhere</option>
              {Object.entries(SOURCE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            {data.evidence_options?.length > 1 && (
              <select value={f.evidence} onChange={set('evidence')}>
                <option value="">All files</option>
                {data.evidence_options.map((e) => <option key={e.id} value={e.id}>{e.original_filename}</option>)}
              </select>
            )}
            <div className="spacer" />
            <ExportButtons caseId={caseId} which="deleted" params={f} fileAccess={summary.file_access} onDone={setSuccess} onError={setError} />
          </div>

          {data.results.length === 0 ? (
            <div className="empty-state"><h3>No matching records</h3><p>Try clearing your filters.</p></div>
          ) : (
            <>
              <table className="table">
                <thead>
                  <tr>
                    <th>Time</th><th>Type</th><th>Recovered item</th><th>Status</th><th>Confidence</th><th>Found in</th><th>File</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((r) => (
                    <tr key={r.id}>
                      <td className="nowrap">{fmtTime(r.event_time)}</td>
                      <td>{KIND_LABEL[r.kind] || r.kind}</td>
                      <td className="wrap">
                        <div>{r.primary}</div>
                        {r.secondary && <div className="muted">{r.secondary}</div>}
                        {r.kind === 'cookie' && <div className="muted">value not recovered (protected)</div>}
                        {r.kind === 'login' && <div className="muted">password not recovered (protected)</div>}
                      </td>
                      <td>
                        <Chip kind={r.status === 'wal_only' ? 'info' : r.status === 'older_version' ? 'neutral' : 'warn'}>
                          {STATUS_LABEL[r.status] || r.status}
                        </Chip>
                        {r.detail?.deleted_in_wal && <div className="muted">deleted in WAL</div>}
                      </td>
                      <td><Conf level={r.confidence} /></td>
                      <td title={`page ${r.page_no ?? '?'}, offset ${r.offset ?? '?'}${r.rowid != null ? `, rowid ${r.rowid}` : ''}`}>
                        {SOURCE_LABEL[r.source] || r.source}
                      </td>
                      <td className="wrap muted">{r.evidence_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {pager}
            </>
          )}
        </>
      )}

      <div className="note-box">
        <strong>Read this before relying on results</strong>
        <ul>
          {summary.limitations.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </div>
    </>
  )
}
