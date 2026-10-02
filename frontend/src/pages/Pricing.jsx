import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../api/AuthContext'
import FileAccessBadges from '../components/FileAccessBadges'
import Banner from '../components/Banner'

const fmtINR = (n) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n)

export default function Pricing() {
  const { me } = useAuth()
  const navigate = useNavigate()
  const [plans, setPlans] = useState([])
  const [cycle, setCycle] = useState('monthly')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyKey, setBusyKey] = useState('')

  useEffect(() => {
    api
      .plans()
      .then(setPlans)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const currentPlanId = me?.organization?.plan?.id

  async function handleChoose(plan) {
    setError('')
    if (!me?.authenticated) {
      navigate('/login?next=/pricing')
      return
    }
    if (!me.is_org_owner) {
      setError('Only the organization owner can change the subscription plan.')
      return
    }
    if (plan.is_free) {
      setBusyKey(plan.key)
      try {
        await api.modifySubscription(plan.key, cycle)
        navigate('/billing')
      } catch (e) {
        setError(e.message)
      } finally {
        setBusyKey('')
      }
      return
    }
    navigate(`/checkout/${plan.key}/${cycle}`)
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Plans built around case volume</h1>
        <p className="page-sub">
          Every plan is priced by how many active cases your organization runs, billed monthly or
          yearly. Admins can adjust pricing, case limits, and which file formats each plan unlocks
          at any time from Manage Plans.
        </p>
      </div>

      <div className="cycle-toggle">
        <button className={cycle === 'monthly' ? 'active' : ''} onClick={() => setCycle('monthly')}>
          Monthly
        </button>
        <button className={cycle === 'yearly' ? 'active' : ''} onClick={() => setCycle('yearly')}>
          Yearly
          <span className="save-tag">save vs monthly</span>
        </button>
      </div>

      <Banner kind="danger" onClose={() => setError('')}>
        {error}
      </Banner>

      {loading ? (
        <div className="loading">Loading plans…</div>
      ) : (
        <div className="plan-grid">
          {plans.map((plan) => {
            const price = cycle === 'yearly' ? plan.yearly_price_inr : plan.monthly_price_inr
            const isCurrent = currentPlanId === plan.id
            return (
              <div key={plan.id} className={`plan-card ${isCurrent ? 'current' : ''}`}>
                {isCurrent && <div className="plan-badge">Current plan</div>}
                <h2>{plan.name}</h2>
                <p className="plan-tagline">{plan.tagline}</p>
                <div className="plan-price">
                  {plan.is_free ? (
                    <span className="amount">Free</span>
                  ) : (
                    <>
                      <span className="amount">{fmtINR(price)}</span>
                      <span className="period">/{cycle === 'yearly' ? 'yr' : 'mo'}</span>
                    </>
                  )}
                </div>
                <div className="plan-cases">
                  {plan.max_cases === 0 ? (
                    'Unlimited cases'
                  ) : cycle === 'yearly' ? (
                    <>
                      Up to {plan.max_cases_yearly} active case{plan.max_cases_yearly === 1 ? '' : 's'}
                      {plan.yearly_case_bonus > 0 && (
                        <span className="save-tag"> +{plan.yearly_case_bonus} yearly bonus</span>
                      )}
                    </>
                  ) : (
                    <>
                      Up to {plan.max_cases} active case{plan.max_cases === 1 ? '' : 's'}
                      {plan.yearly_case_bonus > 0 && (
                        <span className="plan-hint"> ({plan.max_cases_yearly} on yearly billing)</span>
                      )}
                    </>
                  )}
                  <br />
                  {plan.max_evidence_per_case === 0
                    ? 'Unlimited evidence per case'
                    : `${plan.max_evidence_per_case} evidence file${plan.max_evidence_per_case === 1 ? '' : 's'}/case`}
                </div>

                <ul className="plan-features">
                  {plan.features.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                  {plan.features.length === 0 && <li className="muted">Core case tracking only</li>}
                </ul>

                <FileAccessBadges fileAccess={plan.file_access} />

                <button
                  className={`btn ${isCurrent ? 'btn-ghost' : 'btn-primary'} btn-block`}
                  disabled={isCurrent || busyKey === plan.key}
                  onClick={() => handleChoose(plan)}
                >
                  {isCurrent ? 'Current plan' : busyKey === plan.key ? 'Please wait…' : plan.is_free ? 'Switch to Free' : 'Choose plan'}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
