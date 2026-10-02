import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { casesApi } from '../api/client'
import Banner from '../components/Banner'
import Badge from '../components/Badge'
import Pagination from '../components/Pagination'
import PlanLimitNotice from '../components/PlanLimitNotice'

export default function CaseList() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  function load() {
    casesApi
      .list({ q, status, page })
      .then(setData)
      .catch((e) => setError(e.message))
  }

  useEffect(load, [q, status, page])

  return (
    <div className="page">
      <div className="page-head">
        <h1>Cases</h1>
        <p className="page-sub">Every case your organization is running, scoped to your role.</p>
      </div>

      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>

      <div className="toolbar">
        <input
          type="search"
          placeholder="Search cases…"
          value={q}
          onChange={(e) => {
            setPage(1)
            setQ(e.target.value)
          }}
        />
        <select
          value={status}
          onChange={(e) => {
            setPage(1)
            setStatus(e.target.value)
          }}
        >
          <option value="">All statuses</option>
          {(data?.statuses || []).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <div className="spacer" />
        {data?.can_create && (
          <Link
            className="btn btn-primary"
            to="/cases/new"
            style={{
              pointerEvents: data.case_usage.allowed && !data.is_read_only ? 'auto' : 'none',
              opacity: data.case_usage.allowed && !data.is_read_only ? 1 : 0.5,
            }}
          >
            + New case
          </Link>
        )}
      </div>

      {data?.is_read_only && (
        <PlanLimitNotice>The Free plan is view-only — upgrade to create or edit cases.</PlanLimitNotice>
      )}
      {data && !data.is_read_only && !data.case_usage.unlimited && !data.case_usage.allowed && (
        <PlanLimitNotice>
          Your plan allows {data.case_usage.limit} case(s) and you're at the limit ({data.case_usage.used} used).
        </PlanLimitNotice>
      )}

      {!data ? (
        <div className="loading">Loading cases…</div>
      ) : data.results.length === 0 ? (
        <div className="empty-state">
          <h3>No cases found</h3>
          <p>Try adjusting your search or filters.</p>
        </div>
      ) : (
        <>
          <div className="case-grid">
            {data.results.map((c) => (
              <Link key={c.id} className="case-card" to={`/cases/${c.id}`}>
                <div className="case-card-head">
                  <div>
                    <div className="case-card-num">{c.case_number}</div>
                    <h3 className="case-card-name">{c.name}</h3>
                  </div>
                  <Badge kind={c.status} />
                </div>
                <div className="case-card-meta">
                  <Badge kind={c.priority} />
                  <span>{c.evidence_count} evidence file{c.evidence_count === 1 ? '' : 's'}</span>
                  <span>{c.investigator_name || c.investigator_username}</span>
                </div>
                {c.tags && (
                  <div className="case-card-tags">
                    {c.tags.split(',').map((t) => t.trim()).filter(Boolean).map((t) => (
                      <span key={t} className="tag-pill">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </Link>
            ))}
          </div>
          <Pagination count={data.count} pageSize={15} page={page} onChange={setPage} />
        </>
      )}
    </div>
  )
}
