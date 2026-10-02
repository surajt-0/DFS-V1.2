import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../api/AuthContext'

export function RequireAuth({ children }) {
  const { me, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page loading">Loading…</div>
  if (!me?.authenticated) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
  }
  return children
}

export function RequireAdmin({ children }) {
  const { me, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page loading">Loading…</div>
  if (!me?.authenticated) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
  }
  if (!me.is_superuser) return <Navigate to="/pricing" replace />
  return children
}
