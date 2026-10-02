import { useState } from 'react'
import { Link } from 'react-router-dom'
import { recoveryApi } from '../../api/client'
import Banner from '../../components/Banner'
import { Chip, ExportButtons, fmtTime, usePagedList } from './common'

const TYPES = [
  ['hosts', 'Hosts file'], ['cache', 'DNS cache'], ['resolver', 'Resolvers'],
  ['search_domain', 'Search domains'], ['dns_setting', 'Settings'], ['lookup', 'Active lookups'],
]
const ORIGIN = { uploaded: 'Uploaded evidence', local_machine: 'This computer', active_lookup: 'Active lookup' }
const FLAG = {
  redirect_known_domain: ['danger', 'Well-known domain redirected'],
  blocked_known_domain: ['warn', 'Well-known domain blocked'],
  blocked: ['neutral', 'Blocked'],
}

function Entries({ caseId, summary, refreshKey, setSuccess, setError }) {
  const [f, setF] = useState({ type: '', severity: '', origin: '', q: '' })
  const { data, pager } = usePagedList(caseId, 'dnsEntries', f, true, refreshKey)
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }))
  const dns = useBrowserDnsSettings(caseId, refreshKey)
  return (
    <>
      <div className="toolbar">
        <input type="search" placeholder="Search name or value…" value={f.q} onChange={set('q')} />
        <select value={f.type} onChange={set('type')}>
          <option value="">All types</option>
          {TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <select value={f.severity} onChange={set('severity')}>
          <option value="">Any severity</option>
          <option value="alert">Alerts</option>
          <option value="warn">Warnings</option>
          <option value="info">Info</option>
        </select>
        <select value={f.origin} onChange={set('origin')}>
          <option value="">Any origin</option>
          {Object.entries(ORIGIN).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <div className="spacer" />
        <ExportButtons caseId={caseId} which="dnsEntries" params={f} fileAccess={summary.file_access} onDone={setSuccess} onError={setError} />
      </div>
      {!data ? <div className="loading">Loading…</div> : data.results.length === 0 ? (
        <div className="empty-state">
          <h3>No DNS data yet</h3>
          <p>
            Upload a <code>hosts</code> file or a saved DNS-cache / resolver export (<code>ipconfig /displaydns</code>,
            <code> scutil --dns</code>, <code>resolvectl status</code>, <code>resolv.conf</code>)
            {summary.local_dns_available ? ', or collect from this computer.' : '.'}
          </p>
          <Link className="btn btn-ghost" to={`/cases/${caseId}/upload`}>Upload evidence</Link>
        </div>
      ) : (
        <>
          <table className="table">
            <thead><tr><th>Type</th><th>Name</th><th>Value</th><th>Record</th><th>TTL</th><th>Finding</th><th>Origin</th></tr></thead>
            <tbody>
              {data.results.map((r) => {
                const fl = FLAG[r.flag]
                return (
                  <tr key={r.id}>
                    <td>{TYPES.find(([k]) => k === r.type)?.[1] || r.type}</td>
                    <td className="wrap">{r.name}</td>
                    <td className="wrap">{r.value || '—'}</td>
                    <td>{r.record_type || '—'}</td>
                    <td>{r.ttl ?? '—'}</td>
                    <td>{fl ? <Chip kind={fl[0]}>{fl[1]}</Chip> : <span className="muted">—</span>}
                      {r.detail?.comment && <div className="muted">{r.detail.comment}</div>}</td>
                    <td className="muted">
                      {ORIGIN[r.origin] || r.origin}
                      <div>{r.evidence_name || fmtTime(r.observed_at)}</div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {pager}
        </>
      )}
      {dns.length > 0 && (
        <div className="note-box">
          <strong>DNS-related browser settings found in uploaded preferences</strong>
          <ul>{dns.map((d) => <li key={d.id}><code>{d.name}</code> = {d.value}</li>)}</ul>
        </div>
      )}
    </>
  )
}

function useBrowserDnsSettings(caseId, refreshKey) {
  const { data } = usePagedList(caseId, 'state', { category: 'preference', dns: '1' }, true, refreshKey)
  return data?.results || []
}

function Domains({ caseId, summary, onLookupDone, setSuccess, setError }) {
  const [f, setF] = useState({ q: '', only_recovered: false })
  const { data, pager } = usePagedList(caseId, 'domains', { q: f.q, only_recovered: f.only_recovered ? '1' : '' })
  const [sel, setSel] = useState({})
  const [busy, setBusy] = useState(false)
  const chosen = Object.keys(sel).filter((k) => sel[k])

  async function lookup() {
    const ok = window.confirm(
      `Look up ${chosen.length} domain(s) now?\n\n` +
        'This contacts DNS servers from this computer. The lookup can be logged by whoever runs those servers, ' +
        'and the answers describe DNS today — not what the subject\'s machine saw at the time of the events.'
    )
    if (!ok) return
    setBusy(true)
    setError('')
    try {
      const r = await recoveryApi.lookup(caseId, chosen)
      const bad = r.failed.length + r.invalid.length
      setSuccess(`Looked up ${r.looked_up} domain(s): ${r.records} record(s) stored${bad ? `, ${bad} had no answer or were invalid` : ''}. See “Hosts, resolvers & lookups”.`)
      setSel({})
      onLookupDone()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <p className="muted">Every host mentioned anywhere in this case's data — including hosts that appear <em>only</em> in recovered (deleted) records.</p>
      <div className="toolbar">
        <input type="search" placeholder="Filter domains…" value={f.q} onChange={(e) => setF((p) => ({ ...p, q: e.target.value }))} />
        <label className="check-row" style={{ margin: 0 }}>
          <input type="checkbox" checked={f.only_recovered} onChange={(e) => setF((p) => ({ ...p, only_recovered: e.target.checked }))} />
          <span>Only in recovered data</span>
        </label>
        <div className="spacer" />
        <button className="btn btn-ghost btn-sm" disabled={!summary.can_run || busy || chosen.length === 0} onClick={lookup}
          title="Active lookups contact DNS servers — you'll be asked to confirm">
          {busy ? 'Looking up…' : `Look up selected (${chosen.length})`}
        </button>
        <ExportButtons caseId={caseId} which="domains" params={{ q: f.q, only_recovered: f.only_recovered ? '1' : '' }} fileAccess={summary.file_access} onDone={setSuccess} onError={setError} />
      </div>
      {!data ? <div className="loading">Loading…</div> : data.results.length === 0 ? (
        <div className="empty-state"><h3>No domains found</h3><p>Upload History, Cookies or Downloads evidence, or run deleted-data recovery.</p></div>
      ) : (
        <>
          <table className="table">
            <thead><tr><th /><th>Domain</th><th>Mentions</th><th>Live</th><th>Recovered</th><th>First seen</th><th>Last seen</th><th>Seen in</th></tr></thead>
            <tbody>
              {data.results.map((d) => (
                <tr key={d.domain}>
                  <td>{!d.is_ip && <input type="checkbox" checked={!!sel[d.domain]} onChange={(e) => setSel((p) => ({ ...p, [d.domain]: e.target.checked }))} aria-label={`Select ${d.domain}`} />}</td>
                  <td className="wrap">{d.domain}{d.only_in_recovered && <> <Chip kind="warn" title="Not present in any live data">only in recovered</Chip></>}</td>
                  <td>{d.total}</td><td>{d.live}</td><td>{d.recovered}</td>
                  <td className="nowrap">{fmtTime(d.first_seen)}</td><td className="nowrap">{fmtTime(d.last_seen)}</td>
                  <td className="muted">{Object.entries(d.sources).map(([k, v]) => `${k} ${v}`).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {pager}
        </>
      )}
    </>
  )
}

export default function DnsTab({ caseId, summary, reloadSummary, setSuccess, setError }) {
  const [view, setView] = useState('entries')
  const [tick, setTick] = useState(0)
  const [busy, setBusy] = useState(false)
  const alerts = summary.counts.dns.alerts

  async function collectLocal() {
    setBusy(true)
    setError('')
    try {
      const r = await recoveryApi.scanLocalDns(caseId)
      setSuccess(`Collected ${r.stored} DNS row(s) from this ${r.platform} computer. ${r.notes.join(' ')}`)
      await reloadSummary()
      setTick((t) => t + 1)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function clearLookups() {
    if (!window.confirm('Remove all stored active-lookup results for this case?')) return
    try {
      const r = await recoveryApi.clearLookups(caseId)
      setSuccess(`Removed ${r.removed} lookup row(s).`)
      setTick((t) => t + 1)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <>
      <p className="page-sub">
        Hosts-file tampering checks, resolver configuration and DNS-cache contents, plus every domain the case's data
        touches. Nothing here uses the network unless you explicitly run a lookup.
      </p>
      {alerts > 0 && (
        <Banner kind="danger">
          {alerts} hosts-file entr{alerts === 1 ? 'y maps' : 'ies map'} a well-known domain to a non-local address — a
          common sign of redirection or phishing. Filter by severity “Alerts”.
        </Banner>
      )}
      <div className="toolbar" style={{ marginTop: 12 }}>
        {summary.local_dns_available && (
          <button className="btn btn-primary btn-sm" disabled={!summary.can_run || busy} onClick={collectLocal}
            title="Reads this computer's hosts file, resolver settings and (Windows) DNS cache">
            {busy ? 'Collecting…' : 'Collect from this computer'}
          </button>
        )}
        <button className="btn btn-ghost btn-sm" onClick={clearLookups} disabled={!summary.can_run}>Clear stored lookups</button>
      </div>
      <div className="chip-tabs">
        <button className={`chip-tab ${view === 'entries' ? 'active' : ''}`} onClick={() => setView('entries')}>Hosts, resolvers &amp; lookups</button>
        <button className={`chip-tab ${view === 'domains' ? 'active' : ''}`} onClick={() => setView('domains')}>Domains in this case</button>
      </div>
      {view === 'entries'
        ? <Entries caseId={caseId} summary={summary} refreshKey={tick} setSuccess={setSuccess} setError={setError} />
        : <Domains caseId={caseId} summary={summary} onLookupDone={() => { setTick((t) => t + 1); setView('entries') }} setSuccess={setSuccess} setError={setError} />}
    </>
  )
}
