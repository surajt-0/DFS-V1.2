import { useNavigate } from 'react-router-dom'

/**
 * Small "‹ Back" control used across the SPA. Prefers real browser history
 * (so it lands wherever the user actually came from, including query/filter
 * state on list pages) and falls back to a fixed route -- useful for deep
 * links or a freshly-opened tab where there's no SPA history to go back to.
 */
export default function BackButton({ fallback = '/dashboard', label = 'Back', className = '' }) {
  const navigate = useNavigate()

  function onClick() {
    if (window.history.state && window.history.state.idx > 0) {
      navigate(-1)
    } else {
      navigate(fallback)
    }
  }

  return (
    <button type="button" className={`back-btn ${className}`} onClick={onClick} aria-label={label}>
      <span className="back-btn-arrow" aria-hidden="true">‹</span>
      {label}
    </button>
  )
}
