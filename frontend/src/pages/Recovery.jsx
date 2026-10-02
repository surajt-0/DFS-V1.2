import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { casesApi, recoveryApi } from '../api/client'
import Banner from '../components/Banner'
import PlanLimitNotice from '../components/PlanLimitNotice'
import DeletedTab from './recovery/DeletedTab'
import DnsTab from './recovery/DnsTab'
import SystemTab from './recovery/SystemTab'

const TABS = [
  ['deleted', 'Deleted data', 'data_recovery'],
  ['system', 'Browser system data', 'data_recovery'],
  ['dns', 'DNS details', 'dns_details'],
]

export default function Recovery() {
  const { id: caseId, tab } = useParams()
  const [caseName, setCaseName] = useState('')
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    casesApi.detail(caseId).then((c) => setCaseName(c.name)).catch(() => {})
  }, [caseId])

  const reloadSummary = useCallback(
    () => recoveryApi.summary(caseId).then(setSummary).catch((e) => setError(e.message)),
    [caseId]
  )
  useEffect(() => {
    reloadSummary()
  }, [reloadSummary])

  const active = TABS.find(([k]) => k === tab) || TABS[0]
  const enabled = summary?.enabled?.[active[2]]

  return (
    <div className="page">
      <div className="page-head">
        <h1>Recovery &amp; DNS</h1>
        <p className="page-sub">
          <Link to={`/cases/${caseId}`}>{caseName || `Case #${caseId}`}</Link>
        </p>
      </div>

      <div className="tabs">
        {TABS.map(([k, label]) => (
          <Link key={k} to={`/cases/${caseId}/recovery/${k}`} className={k === active[0] ? 'active' : ''}>
            {label}
          </Link>
        ))}
      </div>

      <Banner kind="danger" onClose={() => setError('')}>{error}</Banner>
      <Banner kind="success" onClose={() => setSuccess('')}>{success}</Banner>

      {!summary ? (
        !error && <div className="loading">Loading…</div>
      ) : !enabled ? (
        <PlanLimitNotice>{active[1]} isn't included on your current plan.</PlanLimitNotice>
      ) : (
        <div style={{ marginTop: 16 }}>
          {active[0] === 'deleted' && (
            <DeletedTab caseId={caseId} summary={summary} reloadSummary={reloadSummary} setSuccess={setSuccess} setError={setError} />
          )}
          {active[0] === 'system' && <SystemTab caseId={caseId} summary={summary} setSuccess={setSuccess} setError={setError} />}
          {active[0] === 'dns' && (
            <DnsTab caseId={caseId} summary={summary} reloadSummary={reloadSummary} setSuccess={setSuccess} setError={setError} />
          )}
        </div>
      )}
    </div>
  )
}
