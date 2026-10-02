import { useEffect, useState } from 'react'
import { api } from '../api/client'
import Banner from '../components/Banner'

const FEATURE_FIELDS = [
  { key: 'feature_csv_export', label: 'CSV export' },
  { key: 'feature_xlsx_export', label: 'XLSX export' },
  { key: 'feature_json_export', label: 'JSON export' },
  { key: 'feature_pdf_reports', label: 'Chain-of-custody PDF reports' },
  { key: 'feature_audit_log', label: 'Full audit log access' },
  { key: 'feature_local_scan', label: 'Local workstation scan' },
  { key: 'feature_data_recovery', label: 'Deleted-data & browser system-data recovery' },
  { key: 'feature_dns_details', label: 'DNS details' },
  { key: 'feature_priority_support', label: 'Priority support' },
  { key: 'feature_custom_branding', label: 'Custom branding' },
  { key: 'feature_sso', label: 'SSO / SAML' },
]

function PlanEditor({ plan, onSave }) {
  const [form, setForm] = useState(plan)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [ok, setOk] = useState(false)

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
    setDirty(true)
    setOk(false)
  }

  async function save() {
    setSaving(true)
    setError('')
    try {
      const updated = await onSave(plan.id, {
        monthly_price_inr: form.monthly_price_inr,
        yearly_price_inr: form.yearly_price_inr,
        max_cases: form.max_cases,
        yearly_case_bonus: form.yearly_case_bonus,
        max_evidence_per_case: form.max_evidence_per_case,
        is_public: form.is_public,
        ...Object.fromEntries(FEATURE_FIELDS.map((f) => [f.key, form[f.key]])),
      })
      setForm(updated)
      setDirty(false)
      setOk(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="admin-plan-card">
      <div className="admin-plan-head">
        <h2>{form.name}</h2>
        <label className="switch">
          <input type="checkbox" checked={form.is_public} onChange={(e) => set('is_public', e.target.checked)} />
          <span>Public (shown on pricing page)</span>
        </label>
      </div>

      <div className="admin-field-row">
        <label>
          Monthly price (₹)
          <input
            type="number"
            min="0"
            step="0.01"
            value={form.monthly_price_inr}
            onChange={(e) => set('monthly_price_inr', e.target.value)}
          />
        </label>
        <label>
          Yearly price (₹)
          <input
            type="number"
            min="0"
            step="0.01"
            value={form.yearly_price_inr}
            onChange={(e) => set('yearly_price_inr', e.target.value)}
          />
        </label>
      </div>

      <div className="admin-field-row">
        <label>
          Max active cases (monthly) <span className="hint">(0 = unlimited)</span>
          <input type="number" min="0" value={form.max_cases} onChange={(e) => set('max_cases', e.target.value)} />
        </label>
        <label>
          Max evidence per case <span className="hint">(0 = unlimited)</span>
          <input
            type="number"
            min="0"
            value={form.max_evidence_per_case}
            onChange={(e) => set('max_evidence_per_case', e.target.value)}
          />
        </label>
      </div>

      <div className="admin-field-row">
        <label>
          Yearly bonus cases <span className="hint">(added on top of the monthly limit for yearly billing; ignored if max cases = 0)</span>
          <input
            type="number"
            min="0"
            value={form.yearly_case_bonus}
            onChange={(e) => set('yearly_case_bonus', e.target.value)}
          />
        </label>
        <div className="admin-yearly-preview hint">
          {Number(form.max_cases) === 0
            ? 'Unlimited on both cycles'
            : `Yearly subscribers get ${Number(form.max_cases) + Number(form.yearly_case_bonus || 0)} cases`}
        </div>
      </div>

      <div className="admin-feature-title">File &amp; feature access for this plan</div>
      <div className="admin-feature-grid">
        {FEATURE_FIELDS.map((f) => (
          <label key={f.key} className="switch">
            <input type="checkbox" checked={!!form[f.key]} onChange={(e) => set(f.key, e.target.checked)} />
            <span>{f.label}</span>
          </label>
        ))}
      </div>

      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>
      {ok && <Banner kind="success">Saved.</Banner>}

      <button className="btn btn-primary" disabled={!dirty || saving} onClick={save}>
        {saving ? 'Saving…' : 'Save changes'}
      </button>
    </div>
  )
}

export default function AdminPlans() {
  const [plans, setPlans] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .adminPlans()
      .then(setPlans)
      .catch((e) => setError(e.message))
  }, [])

  async function handleSave(planId, payload) {
    const updated = await api.updatePlan(planId, payload)
    setPlans((prev) => prev.map((p) => (p.id === planId ? updated : p)))
    return updated
  }

  if (error) {
    return (
      <div className="page">
        <Banner kind="danger">{error}</Banner>
      </div>
    )
  }

  if (!plans) {
    return (
      <div className="page">
        <div className="loading">Loading plans…</div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Manage Plans</h1>
        <p className="page-sub">
          Set the price, case-volume limit, and which file formats/features each subscription tier
          unlocks. Changes apply to new checkouts and future limit checks immediately.
        </p>
      </div>
      <div className="admin-plan-grid">
        {plans.map((plan) => (
          <PlanEditor key={plan.id} plan={plan} onSave={handleSave} />
        ))}
      </div>
    </div>
  )
}
