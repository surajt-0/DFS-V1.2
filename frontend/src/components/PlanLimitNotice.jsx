import { Link } from 'react-router-dom'

export default function PlanLimitNotice({ children }) {
  if (!children) return null
  return (
    <div className="locked-note">
      <span>🔒 {children}</span>
      <Link to="/pricing">Upgrade plan →</Link>
    </div>
  )
}
