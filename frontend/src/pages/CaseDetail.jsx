import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { casesApi, evidenceApi } from '../api/client'
import { useAuth } from '../api/AuthContext'
import Banner from '../components/Banner'
import Badge from '../components/Badge'
import PlanLimitNotice from '../components/PlanLimitNotice'

const fmtDate = (d) =>
  d ? new Date(d).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' }) : '—'

const bytesFmt = (n) => {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(1)} ${units[i]}`
}

const ARTIFACT_KINDS = [
  { kind: 'history', label: 'History' },
  { kind: 'login', label: 'Logins' },
  { kind: 'cookie', label: 'Cookies' },
  { kind: 'download', label: 'Downloads' },
  { kind: 'cache', label: 'Cache' },
]

export default function CaseDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { me } = useAuth()
  const [caseObj, setCaseObj] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [downloadingReport, setDownloadingReport] = useState(false)

  function load() {
    casesApi.detail(id).then(setCaseObj).catch((e) => setError(e.message))
  }
  useEffect(load, [id])

  async function handleStatus(newStatus) {
    setBusy(true)
    setError('')
    try {
      const updated = await casesApi.setStatus(id, newStatus)
      setCaseObj(updated)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleDownloadReport() {
    setDownloadingReport(true)
    setError('')
    setSuccess('')
    try {
      const filename = await casesApi.downloadReport(id)
      setSuccess(`Downloaded ${filename}.`)
    } catch (e) {
      setError(e.message)
    } finally {
      setDownloadingReport(false)
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Delete case ${caseObj.case_number}? This cannot be undone.`)) return
    setBusy(true)
    try {
      await casesApi.remove(id)
      navigate('/cases')
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  async function handleReparse(evidenceId) {
    setBusy(true)
    setError('')
    try {
      await evidenceApi.reparse(evidenceId)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleDeleteEvidence(evidenceId, filename) {
    if (!window.confirm(`Delete evidence file "${filename}"?`)) return
    setBusy(true)
    try {
      await evidenceApi.remove(evidenceId)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (error && !caseObj) {
    return (
      <div className="page">
        <Banner kind="danger">{error}</Banner>
      </div>
    )
  }
  if (!caseObj) return <div className="page loading">Loading case…</div>

  const plan = me?.organization?.plan
  const canEdit = caseObj.can_edit
  // Evidence upload has its own permission: on a paid plan every role can add
  // evidence to a case they can see, without gaining full edit rights.
  const canUpload = caseObj.can_upload_evidence
  const evidenceLimit = plan?.max_evidence_per_case ?? 0
  const atEvidenceLimit = evidenceLimit > 0 && caseObj.evidence_count >= evidenceLimit

  return (
    <div className="page">
      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>
      <Banner kind="success" onClose={() => setSuccess('')}>
        {success}
      </Banner>

      <div className="detail-head">
        <div className="detail-head-left">
          <div className="case-card-num">{caseObj.case_number}</div>
          <h1>{caseObj.name}</h1>
          <div className="case-card-meta">
            <Badge kind={caseObj.status} />
            <Badge kind={caseObj.priority} />
          </div>
        </div>
        <div className="detail-actions">
          {canEdit && (
            <>
              <Link className="btn btn-ghost" to={`/cases/${id}/edit`}>
                Edit
              </Link>
              {caseObj.status !== 'closed' ? (
                <button className="btn btn-ghost" disabled={busy} onClick={() => handleStatus('closed')}>
                  Mark closed
                </button>
              ) : (
                <button className="btn btn-ghost" disabled={busy} onClick={() => handleStatus('open')}>
                  Reopen
                </button>
              )}
              <button className="btn btn-danger-ghost" disabled={busy} onClick={handleDelete}>
                Delete
              </button>
            </>
          )}
          <button
            className="btn btn-ghost"
            onClick={handleDownloadReport}
            disabled={downloadingReport}
            title={plan?.file_access?.pdf_reports ? 'Download chain-of-custody PDF' : 'Requires a plan with PDF reports'}
          >
            {downloadingReport ? 'Generating…' : 'PDF report'}
          </button>
        </div>
      </div>

      {!plan?.file_access?.pdf_reports && (
        <PlanLimitNotice>Chain-of-custody PDF reports aren't included on your current plan.</PlanLimitNotice>
      )}

      {caseObj.description && <p className="muted">{caseObj.description}</p>}

      <div className="meta-grid">
        <div className="meta-item">
          <div className="meta-item-label">Investigator</div>
          <div className="meta-item-value">{caseObj.investigator_name || caseObj.investigator_username}</div>
        </div>
        <div className="meta-item">
          <div className="meta-item-label">Subject / custodian</div>
          <div className="meta-item-value">{caseObj.subject_name || '—'}</div>
        </div>
        <div className="meta-item">
          <div className="meta-item-label">Created</div>
          <div className="meta-item-value">{fmtDate(caseObj.created_at)}</div>
        </div>
        <div className="meta-item">
          <div className="meta-item-label">Evidence files</div>
          <div className="meta-item-value">
            {caseObj.evidence_count}
            {evidenceLimit > 0 ? ` / ${evidenceLimit}` : ''}
          </div>
        </div>
      </div>

      {caseObj.tag_list?.length > 0 && (
        <div className="case-card-tags">
          {caseObj.tag_list.map((t) => (
            <span key={t} className="tag-pill">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="section-title">
        <span>Evidence</span>
        {canUpload && (
          <Link
            className="btn btn-primary btn-sm"
            to={`/cases/${id}/upload`}
            style={{ pointerEvents: atEvidenceLimit ? 'none' : 'auto', opacity: atEvidenceLimit ? 0.5 : 1 }}
          >
            + Upload evidence
          </Link>
        )}
      </div>
      {canUpload && atEvidenceLimit && (
        <PlanLimitNotice>
          Your plan allows {evidenceLimit} evidence file(s) per case and this case is at the limit.
        </PlanLimitNotice>
      )}

      <div className="artifact-links">
        {ARTIFACT_KINDS.map(({ kind, label }) => (
          <Link key={kind} className="btn btn-ghost btn-sm" to={`/cases/${id}/artifacts/${kind}`}>
            {label}
          </Link>
        ))}
        <span className="artifact-links-sep" aria-hidden="true" />
        <Link className="btn btn-ghost btn-sm" to={`/cases/${id}/recovery/deleted`}>
          Deleted data
        </Link>
        <Link className="btn btn-ghost btn-sm" to={`/cases/${id}/recovery/system`}>
          Browser system data
        </Link>
        <Link className="btn btn-ghost btn-sm" to={`/cases/${id}/recovery/dns`}>
          DNS details
        </Link>
      </div>

      {caseObj.evidence_items.length === 0 ? (
        <p className="muted" style={{ marginTop: 16 }}>
          No evidence uploaded yet.
        </p>
      ) : (
        <div className="evidence-list" style={{ marginTop: 16 }}>
          {caseObj.evidence_items.map((ev) => (
            <div key={ev.id} className="evidence-row">
              <div className="evidence-row-main">
                <span className="evidence-row-name">{ev.original_filename}</span>
                <span className="evidence-row-meta">
                  {ev.evidence_type_display} · {bytesFmt(ev.size_bytes)} · {ev.row_count} rows · {fmtDate(ev.uploaded_at)}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Badge kind={ev.status} />
                {canEdit && (
                  <>
                    <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => handleReparse(ev.id)}>
                      Reparse
                    </button>
                    <button
                      className="btn btn-danger-ghost btn-sm"
                      disabled={busy}
                      onClick={() => handleDeleteEvidence(ev.id, ev.original_filename)}
                    >
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
