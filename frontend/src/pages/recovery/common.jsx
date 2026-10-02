import { useEffect, useState } from 'react'
import { recoveryApi } from '../../api/client'
import Pagination from '../../components/Pagination'

export const PAGE_SIZE = 50

export function fmtTime(v) {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString()
}

export function Conf({ level }) {
  const hint = {
    high: 'Complete record, integrity-checked against its own header.',
    medium: 'Decoded and validated; part of the record header was rebuilt from the table schema.',
    low: 'Header reconstructed from the table schema on an assumption — verify before relying on it.',
  }[level]
  return (
    <span className={`conf conf-${level}`} title={hint}>
      {level}
    </span>
  )
}

export function Chip({ kind = 'neutral', children, title }) {
  return (
    <span className={`chip chip-${kind}`} title={title}>
      {children}
    </span>
  )
}

/** Debounced paged list with filters. `params` is the filter object. */
export function usePagedList(caseId, which, params, enabled = true, refreshKey = 0) {
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const key = JSON.stringify(params)

  useEffect(() => setPage(1), [key])
  useEffect(() => {
    if (!enabled) return undefined
    let live = true
    const t = setTimeout(() => {
      recoveryApi
        .list(caseId, which, { ...params, page })
        .then((d) => {
          if (live) {
            setData(d)
            setError('')
          }
        })
        .catch((e) => live && setError(e.message))
    }, 200)
    return () => {
      live = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, which, key, page, enabled, refreshKey])

  return { data, error, page, setPage, pager: data && <Pagination count={data.count} pageSize={PAGE_SIZE} page={page} onChange={setPage} /> }
}

export function ExportButtons({ caseId, which, params, fileAccess, onDone, onError }) {
  const [busy, setBusy] = useState('')
  async function go(fmt) {
    setBusy(fmt)
    try {
      const name = await recoveryApi.downloadExport(caseId, which, fmt, params)
      onDone?.(`Downloaded ${name}.`)
    } catch (e) {
      onError?.(e.message)
    } finally {
      setBusy('')
    }
  }
  const fmts = [['csv', 'CSV'], ['xlsx', 'Excel'], ['json', 'JSON']].filter(([f]) => fileAccess?.[f])
  if (!fmts.length) return null
  return (
    <>
      {fmts.map(([f, label]) => (
        <button key={f} type="button" className="btn btn-ghost btn-sm" disabled={!!busy} onClick={() => go(f)}>
          {busy === f ? 'Exporting…' : `Export ${label}`}
        </button>
      ))}
    </>
  )
}
