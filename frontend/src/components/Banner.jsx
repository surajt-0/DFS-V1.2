export default function Banner({ kind = 'info', children, onClose }) {
  if (!children) return null
  return (
    <div className={`banner banner-${kind}`}>
      <span>{children}</span>
      {onClose && (
        <button className="banner-close" onClick={onClose} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  )
}
