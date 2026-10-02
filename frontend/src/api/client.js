// Thin fetch wrapper for the /api/billing/ JSON API. Auth is Django's own
// session cookie (the user logs in at /accounts/login/ like normal); the
// only extra bit we need client-side is echoing Django's CSRF cookie back
// as a header on unsafe methods.

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
  return match ? decodeURIComponent(match[2]) : null
}

const BASE = '/api/billing'
const CASES_BASE = '/api/cases'
const EVIDENCE_BASE = '/api/evidence'
const AUDIT_BASE = '/api/audit'
const DASHBOARD_BASE = '/api/dashboard'
const ACCOUNTS_BASE = '/api/accounts'
const RECOVERY_BASE = '/api/recovery'

async function requestBase(base, path, { method = 'GET', body, isForm = false } = {}) {
  const headers = {}
  if (!isForm) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') {
    const csrftoken = getCookie('csrftoken')
    if (csrftoken) headers['X-CSRFToken'] = csrftoken
  }

  const res = await fetch(`${base}${path}`, {
    method,
    headers,
    credentials: 'include',
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })

  let data = null
  if (res.status !== 204) {
    try {
      data = await res.json()
    } catch {
      data = null
    }
  }

  if (!res.ok) {
    const message =
      (data && (data.detail || data.message)) ||
      (data && typeof data === 'object' ? Object.values(data).flat().join(' ') : null) ||
      `Request failed (${res.status})`
    const error = new Error(message)
    error.status = res.status
    error.data = data
    throw error
  }
  return data
}

/**
 * Fetches a binary file (CSV/XLSX/JSON export, PDF report) with the same
 * session-cookie auth as every other API call, then saves it via a
 * synthetic `<a download>` click -- instead of a plain `<a href>` link.
 *
 * Two concrete problems this fixes over a plain link:
 *  1. A plain link to an error response (402 plan-limit, 403, etc.) just
 *     navigates the page to raw JSON text with no way back except browser
 *     "back" -- this surfaces the same error message through the normal
 *     Banner UI instead, and the SPA never leaves the page.
 *  2. It gives real success/failure feedback. A native browser download
 *     can succeed completely silently (no visible confirmation, saved to
 *     an OS Downloads folder the user isn't watching), which from the
 *     user's side is indistinguishable from "nothing happened" -- the
 *     caller can show an explicit "Downloaded x.csv" message once this
 *     resolves.
 */
async function downloadFile(url, fallbackFilename) {
  const res = await fetch(url, { credentials: 'include' })

  if (!res.ok) {
    let data = null
    try {
      data = await res.json()
    } catch {
      data = null
    }
    const message =
      (data && (data.detail || data.message)) ||
      (data && typeof data === 'object' ? Object.values(data).flat().join(' ') : null) ||
      `Download failed (${res.status})`
    const error = new Error(message)
    error.status = res.status
    throw error
  }

  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/)
  const filename = (match && match[1]) || fallbackFilename || 'download'

  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Give the browser a moment to actually start the save before revoking.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
  return filename
}

async function request(path, opts) {
  return requestBase(BASE, path, opts)
}

export const api = {
  me: () => request('/me/'),
  plans: () => request('/plans/'),
  mySubscription: () => request('/my/'),
  payments: () => request('/payments/'),
  modifySubscription: (plan_key, cycle) =>
    request('/my/modify/', { method: 'POST', body: { plan_key, cycle } }),
  cancelSubscription: () => request('/my/cancel/', { method: 'POST' }),
  downgradeFree: () => request('/my/downgrade-free/', { method: 'POST' }),
  createCheckout: (planKey, cycle) =>
    request(`/checkout/${planKey}/${cycle}/`, { method: 'POST' }),
  verifyCheckout: (paymentId, payload) =>
    request(`/checkout/${paymentId}/verify/`, { method: 'POST', body: payload }),
  adminPlans: () => request('/admin/plans/'),
  updatePlan: (planId, payload) =>
    request(`/admin/plans/${planId}/`, { method: 'PATCH', body: payload }),
}

// ---------------------------------------------------------------------------
// Accounts (auth + profile)
// ---------------------------------------------------------------------------
export const accountsApi = {
  signup: (payload) => requestBase(ACCOUNTS_BASE, '/signup/', { method: 'POST', body: payload }),
  login: (username, password) =>
    requestBase(ACCOUNTS_BASE, '/login/', { method: 'POST', body: { username, password } }),
  logout: () => requestBase(ACCOUNTS_BASE, '/logout/', { method: 'POST' }),
  profile: () => requestBase(ACCOUNTS_BASE, '/profile/'),
  updateProfile: (payload) => requestBase(ACCOUNTS_BASE, '/profile/', { method: 'PATCH', body: payload }),
  changePassword: (payload) => requestBase(ACCOUNTS_BASE, '/password-change/', { method: 'POST', body: payload }),
}

// ---------------------------------------------------------------------------
// Cases
// ---------------------------------------------------------------------------
export const casesApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null))
    const suffix = qs.toString() ? `/?${qs.toString()}` : '/'
    return requestBase(CASES_BASE, suffix)
  },
  create: (payload) => requestBase(CASES_BASE, '/', { method: 'POST', body: payload }),
  detail: (id) => requestBase(CASES_BASE, `/${id}/`),
  update: (id, payload) => requestBase(CASES_BASE, `/${id}/`, { method: 'PATCH', body: payload }),
  remove: (id) => requestBase(CASES_BASE, `/${id}/`, { method: 'DELETE' }),
  setStatus: (id, newStatus) =>
    requestBase(CASES_BASE, `/${id}/status/${newStatus}/`, { method: 'POST' }),
  reportUrl: (id) => `${CASES_BASE}/${id}/report/`,
  downloadReport: (id) => downloadFile(`${CASES_BASE}/${id}/report/`, `case-${id}-report.pdf`),
}

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------
export const evidenceApi = {
  upload: (casePk, formData) =>
    requestBase(EVIDENCE_BASE, `/case/${casePk}/upload/`, { method: 'POST', body: formData, isForm: true }),
  scanLocal: (casePk, opts = {}) =>
    requestBase(EVIDENCE_BASE, `/case/${casePk}/scan-local/`, { method: 'POST', body: opts }),
  detail: (id) => requestBase(EVIDENCE_BASE, `/${id}/`),
  reparse: (id) => requestBase(EVIDENCE_BASE, `/${id}/reparse/`, { method: 'POST' }),
  remove: (id) => requestBase(EVIDENCE_BASE, `/${id}/`, { method: 'DELETE' }),
  createDemoCase: () => requestBase(EVIDENCE_BASE, '/demo-case/', { method: 'POST' }),
  table: (casePk, kind, params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null))
    const suffix = qs.toString()
      ? `/case/${casePk}/table/${kind}/?${qs.toString()}`
      : `/case/${casePk}/table/${kind}/`
    return requestBase(EVIDENCE_BASE, suffix)
  },
  exportUrl: (casePk, kind, format, extra = {}) => {
    const qs = new URLSearchParams({ export: format, ...extra })
    return `/evidence/case/${casePk}/${TABLE_URL_SEGMENT[kind]}/?${qs.toString()}`
  },
  downloadExport: (casePk, kind, format, extra = {}) =>
    downloadFile(evidenceApi.exportUrl(casePk, kind, format, extra), `case-${casePk}-${kind}.${format}`),
}

// ---------------------------------------------------------------------------
// Recovery: deleted data, browser system data, DNS details
// ---------------------------------------------------------------------------
const RECOVERY_LISTS = {
  deleted: 'deleted',
  state: 'state',
  dnsEntries: 'dns/entries',
  domains: 'dns/domains',
}
// list name -> export "kind" segment understood by recovery/downloads.py
const RECOVERY_EXPORT = { deleted: 'deleted', state: 'state', dnsEntries: 'dns', domains: 'domains' }

function qs(params = {}) {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null && v !== false))
  return s.toString() ? `?${s.toString()}` : ''
}

export const recoveryApi = {
  summary: (casePk) => requestBase(RECOVERY_BASE, `/case/${casePk}/summary/`),
  carve: (casePk, evidenceId) =>
    requestBase(RECOVERY_BASE, `/case/${casePk}/carve/`, {
      method: 'POST',
      body: evidenceId ? { evidence_id: evidenceId } : {},
    }),
  list: (casePk, which, params) =>
    requestBase(RECOVERY_BASE, `/case/${casePk}/${RECOVERY_LISTS[which]}/${qs(params)}`),
  scanLocalDns: (casePk) => requestBase(RECOVERY_BASE, `/case/${casePk}/dns/scan-local/`, { method: 'POST' }),
  lookup: (casePk, domains) =>
    requestBase(RECOVERY_BASE, `/case/${casePk}/dns/lookup/`, { method: 'POST', body: { domains, confirm: true } }),
  clearLookups: (casePk) => requestBase(RECOVERY_BASE, `/case/${casePk}/dns/clear-lookups/`, { method: 'POST' }),
  downloadExport: (casePk, which, format, params = {}) =>
    downloadFile(
      `/recovery/case/${casePk}/${RECOVERY_EXPORT[which]}/${qs({ export: format, ...params })}`,
      `case-${casePk}-${which}.${format}`
    ),
}

// The JSON API path segment (`table/<kind>/`) differs from the legacy
// server-rendered export endpoints (`history/`, `logins/`, ...), which is
// where exports still live (see README) -- map kind -> that URL segment.
const TABLE_URL_SEGMENT = {
  history: 'history',
  login: 'logins',
  cookie: 'cookies',
  download: 'downloads',
  cache: 'cache',
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------
export const auditApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null))
    const suffix = qs.toString() ? `/?${qs.toString()}` : '/'
    return requestBase(AUDIT_BASE, suffix)
  },
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export const dashboardApi = {
  stats: () => requestBase(DASHBOARD_BASE, '/stats/'),
}

