export default function Pagination({ count, pageSize = 15, page, onChange }) {
  const totalPages = Math.max(1, Math.ceil(count / pageSize))
  if (totalPages <= 1) return null

  const pages = []
  const start = Math.max(1, page - 2)
  const end = Math.min(totalPages, start + 4)
  for (let p = start; p <= end; p++) pages.push(p)

  return (
    <div className="pagination">
      <button disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ‹
      </button>
      {start > 1 && <button onClick={() => onChange(1)}>1</button>}
      {start > 2 && <span>…</span>}
      {pages.map((p) => (
        <button key={p} className={p === page ? 'active' : ''} onClick={() => onChange(p)}>
          {p}
        </button>
      ))}
      {end < totalPages - 1 && <span>…</span>}
      {end < totalPages && <button onClick={() => onChange(totalPages)}>{totalPages}</button>}
      <button disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        ›
      </button>
    </div>
  )
}
