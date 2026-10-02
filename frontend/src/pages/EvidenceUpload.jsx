import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { evidenceApi } from '../api/client'
import { useAuth } from '../api/AuthContext'
import Banner from '../components/Banner'

const EVIDENCE_TYPES = [
  ['chromium_history', 'Chromium/Edge/Brave History (SQLite) -- also pulls Downloads automatically'],
  ['firefox_history', 'Firefox places.sqlite'],
  ['safari_history', 'Safari History.db'],
  ['chromium_logins', 'Chromium/Edge/Brave Login Data (SQLite)'],
  ['firefox_logins', 'Firefox logins.json'],
  ['chromium_cookies', 'Chromium/Edge/Brave Cookies (SQLite)'],
  ['firefox_cookies', 'Firefox cookies.sqlite'],
  ['chromium_downloads', 'Chromium/Edge/Brave Downloads (History SQLite, standalone)'],
  ['cache_archive', 'Browser cache folder (.zip)'],
  ['browser_state', 'Browser system data (sessions, Bookmarks, Preferences, extensions, a database -wal file)'],
  ['dns_data', 'DNS data (hosts file, DNS-cache / resolver export)'],
]

function fileKey(f) {
  return `${f.name}-${f.size}-${f.lastModified}`
}

export default function EvidenceUpload() {
  const { id: caseId } = useParams()
  const navigate = useNavigate()
  const { me } = useAuth()
  const plan = me?.organization?.plan

  const [files, setFiles] = useState([])
  const [note, setNote] = useState('')
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [includeSystem, setIncludeSystem] = useState(false)
  const [results, setResults] = useState(null)
  // Manual type override, only offered per-file for anything the last
  // upload attempt couldn't auto-detect.
  const [overrides, setOverrides] = useState({})

  function addFiles(list) {
    const incoming = Array.from(list || [])
    if (!incoming.length) return
    setFiles((prev) => {
      const seen = new Set(prev.map(fileKey))
      return [...prev, ...incoming.filter((f) => !seen.has(fileKey(f)))]
    })
  }

  function removeFile(key) {
    setFiles((prev) => prev.filter((f) => fileKey(f) !== key))
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    addFiles(e.dataTransfer.files)
  }

  async function uploadBatch(fileList, evidenceTypeOverride) {
    const fd = new FormData()
    if (note) fd.append('note', note)
    if (evidenceTypeOverride) fd.append('evidence_type', evidenceTypeOverride)
    fileList.forEach((f) => fd.append('file', f))
    const res = await evidenceApi.upload(caseId, fd)
    return res.results || []
  }

  async function onSubmit(e) {
    e.preventDefault()
    if (!files.length) {
      setError('Add at least one file to upload.')
      return
    }
    setError('')
    setBusy(true)
    try {
      const outcome = await uploadBatch(files)
      setResults(outcome)
      // Only stay on the page if something needs attention (a plan-limit
      // block, or a file that couldn't be auto-detected); a fully clean
      // batch heads straight back to the case.
      const needsAttention = outcome.some((r) => r.status === 'blocked' || r.auto_detected === false || r.parse_warning)
      if (!needsAttention) {
        navigate(`/cases/${caseId}`)
      } else {
        setFiles([])
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleScanLocal() {
    setError('')
    setScanning(true)
    try {
      const res = await evidenceApi.scanLocal(caseId, { include_system_data: includeSystem })
      const outcome = res.results || []
      if (!outcome.length) {
        setError(res.detail || "No browser profile files were found on this computer.")
        return
      }
      setResults(outcome)
      const needsAttention = outcome.some((r) => r.status === 'blocked' || r.auto_detected === false || r.parse_warning)
      if (!needsAttention) {
        navigate(`/cases/${caseId}`)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setScanning(false)
    }
  }

  async function reclassify(filename) {
    const type = overrides[filename]
    if (!type) return
    setError('')
    // Re-send just this one file under the chosen type. The examiner
    // still has the original file on their machine, so this opens a
    // picker scoped to re-selecting it.
    const input = document.createElement('input')
    input.type = 'file'
    input.onchange = async () => {
      if (!input.files?.[0]) return
      setBusy(true)
      try {
        const outcome = await uploadBatch([input.files[0]], type)
        setResults((prev) => [...(prev || []).filter((r) => r.original_filename !== filename), ...outcome])
      } catch (err) {
        setError(err.message)
      } finally {
        setBusy(false)
      }
    }
    input.click()
  }

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1>Upload evidence</h1>
        <p className="page-sub">
          Drop in as many artifact files as you have -- History, Login Data, Cookies, places.sqlite, a cache .zip,
          whatever you've collected. Each one is hashed (SHA-256), its type is detected automatically, and it's
          parsed right away. No need to upload one at a time or pick a type per file.
        </p>
        <p className="page-hint">
          Note on private/incognito sessions: by design, browsers don't write history, cookies, or login data for
          those sessions to the files this suite parses -- there's no separate "incognito" artifact file to detect,
          because the browser itself never created one. What sometimes does survive -- session-restore files,
          DNS cache / hosts file, deleted records still sitting in a database's free space -- is handled by the
          Recovery &amp; DNS tools on the case page (upload those files here too: sessions, Bookmarks, Preferences,
          hosts, a saved <code>ipconfig /displaydns</code> dump, and a database's <code>-wal</code> file).
        </p>
      </div>

      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>

      <div className="card scan-local-card">
        <h3>Automatic: scan this computer</h3>
        <p className="page-sub">
          Finds every installed Chrome, Edge, Brave, Opera, Firefox, and Safari profile on this machine and uploads
          & parses everything it can read automatically -- no file picker needed. Anything it can't read (a file
          locked by a running browser, an unrecognized format) is skipped and reported below; use manual upload
          for those.
        </p>
        {plan?.file_access?.local_scan ? (
          <>
            <label className="check-row">
              <input
                type="checkbox"
                checked={includeSystem}
                disabled={!plan?.file_access?.data_recovery}
                onChange={(e) => setIncludeSystem(e.target.checked)}
              />
              <span>
                Also collect browser system data (open/closed tabs, bookmarks &amp; backups, preferences,
                extensions)
                {!plan?.file_access?.data_recovery && ' — not included on your plan'}
                <span className="muted"> · each file counts toward this case's evidence limit</span>
              </span>
            </label>
            <button type="button" className="btn btn-primary" onClick={handleScanLocal} disabled={scanning || busy}>
              {scanning ? 'Scanning…' : 'Scan this computer for browser data'}
            </button>
          </>
        ) : (
          <p className="page-hint">
            Scanning this computer for browser data isn't included on your current plan. Upgrade to unlock it, or
            use manual upload below.
          </p>
        )}
      </div>

      <div className="divider-label">or upload manually</div>

      {results && (
        <div className="upload-results">
          {results.map((r) => (
            <div key={r.original_filename} className={`upload-result upload-result-${r.status || (r.parse_warning ? 'warning' : 'ok')}`}>
              <div className="upload-result-name">📄 {r.original_filename}</div>
              {r.status === 'blocked' ? (
                <div className="upload-result-detail">{r.detail}</div>
              ) : r.status === 'rejected' ? (
                <div className="upload-result-detail">{r.detail}</div>
              ) : r.auto_detected === false ? (
                <div className="upload-result-detail">
                  Couldn't auto-detect this file's type -- pick one and re-upload it:
                  <div className="upload-result-reclassify">
                    <select
                      value={overrides[r.original_filename] || ''}
                      onChange={(e) => setOverrides((prev) => ({ ...prev, [r.original_filename]: e.target.value }))}
                    >
                      <option value="">Choose type…</option>
                      {EVIDENCE_TYPES.map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={!overrides[r.original_filename] || busy}
                      onClick={() => reclassify(r.original_filename)}
                    >
                      Select file &amp; upload as this type
                    </button>
                  </div>
                </div>
              ) : r.parse_warning ? (
                <div className="upload-result-detail">Uploaded, but parsing failed: {r.parse_warning}</div>
              ) : (
                <div className="upload-result-detail">
                  Detected as <strong>{r.evidence_type_display}</strong> -- parsed {r.row_count} row{r.row_count === 1 ? '' : 's'}.
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <form className="auth-card" onSubmit={onSubmit}>
        <div className="field">
          <label>Files</label>
          <label
            className={`dropzone ${dragging ? 'drag' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            {files.length ? 'Click or drop to add more files' : 'Drag & drop any number of files here, or click to browse'}
            <input type="file" multiple onChange={(e) => addFiles(e.target.files)} />
          </label>
          {files.length > 0 && (
            <div className="file-chip-list">
              {files.map((f) => (
                <div className="file-chip" key={fileKey(f)}>
                  📄 {f.name} · {(f.size / 1024).toFixed(1)} KB
                  <button type="button" className="file-chip-remove" onClick={() => removeFile(fileKey(f))} aria-label={`Remove ${f.name}`}>
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="field">
          <label>Note (optional, applied to every file in this batch)</label>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Extracted from device #3, User Profile A" />
        </div>

        <div className="form-actions">
          <button className="btn btn-primary" disabled={busy || !files.length} type="submit">
            {busy ? 'Uploading…' : `Upload & parse${files.length ? ` (${files.length})` : ''}`}
          </button>
          <button className="btn btn-ghost" type="button" onClick={() => navigate(-1)}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}
