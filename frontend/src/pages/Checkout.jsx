import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import Banner from '../components/Banner'

const fmtINR = (n) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n)

function loadRazorpayScript() {
  return new Promise((resolve) => {
    if (window.Razorpay) return resolve(true)
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => resolve(true)
    script.onerror = () => resolve(false)
    document.body.appendChild(script)
  })
}

export default function Checkout() {
  const { planKey, cycle } = useParams()
  const navigate = useNavigate()
  const [session, setSession] = useState(null)
  const [error, setError] = useState('')
  const [verifying, setVerifying] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    api
      .createCheckout(planKey, cycle)
      .then((data) => {
        if (data.free) {
          navigate('/pricing')
          return
        }
        setSession(data)
      })
      .catch((e) => setError(e.message))
  }, [planKey, cycle, navigate])

  async function verify(payload) {
    setVerifying(true)
    setError('')
    try {
      await api.verifyCheckout(session.payment_id, payload)
      navigate('/billing')
    } catch (e) {
      setError(e.message)
    } finally {
      setVerifying(false)
    }
  }

  async function payWithRazorpay() {
    const ok = await loadRazorpayScript()
    if (!ok || session.demo_mode) {
      return verify({}) // demo mode: nothing to sign, backend accepts it
    }
    const rzp = new window.Razorpay({
      key: session.razorpay_key_id,
      amount: session.amount_paise,
      currency: 'INR',
      name: 'Digital Forensics Browser Suite',
      description: `${session.plan.name} — ${session.cycle}`,
      order_id: session.order.id,
      prefill: { email: session.prefill_email, name: session.prefill_name },
      theme: { color: '#2dd4bf' },
      handler: (response) =>
        verify({
          razorpay_payment_id: response.razorpay_payment_id,
          razorpay_signature: response.razorpay_signature,
        }),
    })
    rzp.open()
  }

  if (error && !session) {
    return (
      <div className="page">
        <Banner kind="danger">{error}</Banner>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="page">
        <div className="loading">Creating your order…</div>
      </div>
    )
  }

  return (
    <div className="page page-narrow">
      <div className="checkout-card">
        <h1>Checkout</h1>
        <div className="checkout-row">
          <span>Plan</span>
          <strong>{session.plan.name}</strong>
        </div>
        <div className="checkout-row">
          <span>Billing cycle</span>
          <strong>{cycle === 'yearly' ? 'Yearly' : 'Monthly'}</strong>
        </div>
        <div className="checkout-row">
          <span>Amount</span>
          <strong>{fmtINR(session.amount_paise / 100)}</strong>
        </div>

        {session.demo_mode && (
          <Banner kind="info">
            Demo mode: no live Razorpay keys are configured, so payment will be simulated locally.
          </Banner>
        )}
        <Banner kind="danger" onClose={() => setError('')}>
          {error}
        </Banner>

        <button className="btn btn-primary btn-block" disabled={verifying} onClick={payWithRazorpay}>
          {verifying ? 'Confirming…' : session.demo_mode ? 'Simulate payment' : 'Pay now'}
        </button>
        <button className="btn btn-ghost btn-block" onClick={() => navigate('/pricing')}>
          Cancel
        </button>
      </div>
    </div>
  )
}
