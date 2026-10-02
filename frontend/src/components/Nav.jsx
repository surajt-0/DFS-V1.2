import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../api/AuthContext'
import { accountsApi } from '../api/client'
import agamyaLogo from '../assets/agamya-logo.jpg'
import BackButton from './BackButton'
import ThemeToggle from './ThemeToggle'

// Pages that are natural "home base" screens for their audience -- no back
// button needed there since there's nowhere more "back" to go.
const NO_BACK_PATHS = new Set(['/', '/dashboard', '/login', '/signup'])

export default function Nav() {
  const { me, loading, refresh } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  async function onLogout() {
    try {
      await accountsApi.logout()
    } finally {
      await refresh()
      navigate('/login')
    }
  }

  const showBack = !NO_BACK_PATHS.has(location.pathname)

  return (
    <header className="nav">
      <div className="nav-inner">
        {showBack && (
          <BackButton
            className="nav-back-btn"
            fallback={me?.authenticated ? '/dashboard' : '/'}
          />
        )}
        <div className="nav-brand">
          <img src={agamyaLogo} alt="Agamya Cyber Tech" className="nav-brand-logo" />
          <span className="nav-brand-mark">DFS</span>
          <span className="nav-brand-name">Digital Forensics Suite</span>
        </div>
        <nav className="nav-links">
          {me?.authenticated && (
            <>
              <NavLink to="/dashboard" end className={({ isActive }) => (isActive ? 'active' : '')}>
                Dashboard
              </NavLink>
              <NavLink to="/cases" className={({ isActive }) => (isActive ? 'active' : '')}>
                Cases
              </NavLink>
              <NavLink to="/audit" className={({ isActive }) => (isActive ? 'active' : '')}>
                Audit Log
              </NavLink>
            </>
          )}
          <NavLink to="/pricing" className={({ isActive }) => (isActive ? 'active' : '')}>
            Pricing
          </NavLink>
          {me?.authenticated && (
            <NavLink to="/billing" className={({ isActive }) => (isActive ? 'active' : '')}>
              My Subscription
            </NavLink>
          )}
          {me?.is_superuser && (
            <NavLink to="/admin/plans" className={({ isActive }) => (isActive ? 'active' : '')}>
              Manage Plans
            </NavLink>
          )}
        </nav>
        <div className="nav-user">
          <ThemeToggle />
          {loading ? (
            <span className="nav-user-loading">…</span>
          ) : me?.authenticated ? (
            <>
              <NavLink to="/profile" className="nav-username">
                {me.username}
                {me.role && <span className="role-pill">{me.role}</span>}
              </NavLink>
              <button className="btn btn-ghost btn-sm" onClick={onLogout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink className="btn btn-ghost btn-sm" to="/login">
                Log in
              </NavLink>
              <NavLink className="btn btn-primary btn-sm" to="/signup">
                Sign up
              </NavLink>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
