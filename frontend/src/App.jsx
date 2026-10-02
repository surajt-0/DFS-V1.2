import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './api/AuthContext'
import { ThemeProvider } from './api/ThemeContext'
import Nav from './components/Nav'
import { RequireAuth, RequireAdmin } from './components/Guard'

import Login from './pages/Login'
import Signup from './pages/Signup'
import Pricing from './pages/Pricing'
import Checkout from './pages/Checkout'
import BillingDashboard from './pages/Dashboard'
import AdminPlans from './pages/AdminPlans'
import DashboardHome from './pages/DashboardHome'
import CaseList from './pages/CaseList'
import CaseForm from './pages/CaseForm'
import CaseDetail from './pages/CaseDetail'
import EvidenceUpload from './pages/EvidenceUpload'
import ArtifactTable from './pages/ArtifactTable'
import Recovery from './pages/Recovery'
import AuditLog from './pages/AuditLog'
import Profile from './pages/Profile'
import './App.css'

function Home() {
  const { me, loading } = useAuth()
  if (loading) return <div className="page loading">Loading…</div>
  return <Navigate to={me?.authenticated ? '/dashboard' : '/pricing'} replace />
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Nav />
          <main className="main">
            <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/pricing" element={<Pricing />} />

            <Route
              path="/checkout/:planKey/:cycle"
              element={
                <RequireAuth>
                  <Checkout />
                </RequireAuth>
              }
            />
            <Route
              path="/billing"
              element={
                <RequireAuth>
                  <BillingDashboard />
                </RequireAuth>
              }
            />
            <Route
              path="/admin/plans"
              element={
                <RequireAdmin>
                  <AdminPlans />
                </RequireAdmin>
              }
            />

            <Route
              path="/dashboard"
              element={
                <RequireAuth>
                  <DashboardHome />
                </RequireAuth>
              }
            />
            <Route
              path="/profile"
              element={
                <RequireAuth>
                  <Profile />
                </RequireAuth>
              }
            />
            <Route
              path="/audit"
              element={
                <RequireAuth>
                  <AuditLog />
                </RequireAuth>
              }
            />

            <Route
              path="/cases"
              element={
                <RequireAuth>
                  <CaseList />
                </RequireAuth>
              }
            />
            <Route
              path="/cases/new"
              element={
                <RequireAuth>
                  <CaseForm />
                </RequireAuth>
              }
            />
            <Route
              path="/cases/:id"
              element={
                <RequireAuth>
                  <CaseDetail />
                </RequireAuth>
              }
            />
            <Route
              path="/cases/:id/edit"
              element={
                <RequireAuth>
                  <CaseForm />
                </RequireAuth>
              }
            />
            <Route
              path="/cases/:id/upload"
              element={
                <RequireAuth>
                  <EvidenceUpload />
                </RequireAuth>
              }
            />
            <Route
              path="/cases/:id/recovery"
              element={<Navigate to="deleted" replace />}
            />
            <Route
              path="/cases/:id/recovery/:tab"
              element={
                <RequireAuth>
                  <Recovery />
                </RequireAuth>
              }
            />
            <Route
              path="/cases/:id/artifacts/:kind"
              element={
                <RequireAuth>
                  <ArtifactTable />
                </RequireAuth>
              }
            />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </main>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  )
}
