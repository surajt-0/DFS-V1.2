import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { casesApi, evidenceApi } from '../api/client'
import Banner from '../components/Banner'
import Pagination from '../components/Pagination'
import PlanLimitNotice from '../components/PlanLimitNotice'

const KIND_LABELS = { history: 'History', login: 'Logins', cookie: 'Cookies', download: 'Downloads', cache: 'Cache' }
const EXPORT_FORMATS = [
  ['csv', 'CSV'],
  ['xlsx', 'Excel'],
  ['json', 'JSON'],
]

function renderCell(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

export default function ArtifactTable() {
  const { id: caseId, kind } = useParams()
  const [caseName, setCaseName] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [downloadingFmt, setDownloadingFmt] = useState('')
  const [q, setQ] = useState('')
  const [evidenceFilter, setEvidenceFilter] = useState('')
  const [sort, setSort] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    casesApi.detail(caseId).then((c) => setCaseName(c.name)).catch(() => {})
  }, [caseId])

  function load() {
    evidenceApi
      .table(caseId, kind, { q, evidence: evidenceFilter, sort, page })
      .then(setData)
      .catch((e) => setError(e.message))
  }
  useEffect(load, [caseId, kind, q, evidenceFilter, sort, page])

  useEffect(() => {
    setQ('')
    setEvidenceFilter('')
    setSort('')
    setPage(1)
  }, [kind])

  function toggleSort(field) {
    setSort((cur) => (cur === field ? `-${field}` : field))
    setPage(1)
  }

  async function handleExport(fmt) {
    setDownloadingFmt(fmt)
    setError('')
    setSuccess('')
    try {
      const filename = await evidenceApi.downloadExport(caseId, kind, fmt, { q, evidence: evidenceFilter, sort })
      setSuccess(`Downloaded ${filename}.`)
    } catch (e) {
      setError(e.message)
    } finally {
      setDownloadingFmt('')
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>{KIND_LABELS[kind] || kind}</h1>
        <p className="page-sub">
          <Link to={`/cases/${caseId}`}>{caseName || `Case #${caseId}`}</Link>
        </p>
      </div>

      <div className="tabs">
        {Object.entries(KIND_LABELS).map(([k, label]) => (
          <Link key={k} to={`/cases/${caseId}/artifacts/${k}`} className={k === kind ? 'active' : ''}>
            {label}
          </Link>
        ))}
      </div>

      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>
      <Banner kind="success" onClose={() => setSuccess('')}>
        {success}
      </Banner>

      {!data ? (
        <div className="loading">Loading…</div>
      ) : (
        <>
          <div className="toolbar">
            <input
              type="search"
              placeholder={`Search ${KIND_LABELS[kind]?.toLowerCase()}…`}
              value={q}
              onChange={(e) => {
                setPage(1)
                setQ(e.target.value)
              }}
            />
            {data.evidence_options.length > 1 && (
              <select
                value={evidenceFilter}
                onChange={(e) => {
                  setPage(1)
                  setEvidenceFilter(e.target.value)
                }}
              >
                <option value="">All evidence files</option>
                {data.evidence_options.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.original_filename}
                  </option>
                ))}
              </select>
            )}
            <div className="spacer" />
            {EXPORT_FORMATS.map(([fmt, label]) =>
              data.file_access[fmt] ? (
                <button
                  key={fmt}
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={downloadingFmt !== ''}
                  onClick={() => handleExport(fmt)}
                >
                  {downloadingFmt === fmt ? 'Exporting…' : `Export ${label}`}
                </button>
              ) : null
            )}
          </div>

          {Object.values(data.file_access).some((v) => !v) && (
            <PlanLimitNotice>
              {EXPORT_FORMATS.filter(([fmt]) => !data.file_access[fmt])
                .map(([, l]) => l)
                .join(' / ')}{' '}
              export isn't included on your current plan.
            </PlanLimitNotice>
          )}

          {data.results.length === 0 ? (
            <div className="empty-state">
              <h3>No rows found</h3>
              <p>Try clearing your search or filters.</p>
            </div>
          ) : (
            <>
              <table className="table" style={{ marginTop: 16 }}>
                <thead>
                  <tr>
                    {data.columns.map((col) => (
                      <th key={col.field} style={{ cursor: 'pointer' }} onClick={() => toggleSort(col.field)}>
                        {col.label} {sort.replace('-', '') === col.field ? (sort.startsWith('-') ? '↓' : '↑') : ''}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((row) => (
                    <tr key={row.id}>
                      {data.columns.map((col) => (
                        <td key={col.field}>{renderCell(row[col.field])}</td>
                      ))}
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
