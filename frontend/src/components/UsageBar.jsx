export default function UsageBar({ label, usage }) {
  if (!usage) return null
  return (
    <div className="usage-bar">
      <div className="usage-label">
        <span>{label}</span>
        <span>
          {usage.used} {usage.unlimited ? '' : `/ ${usage.limit}`}
        </span>
      </div>
      {!usage.unlimited && (
        <div className="usage-track">
          <div
            className="usage-fill"
            style={{ width: `${Math.min(100, (usage.used / Math.max(usage.limit, 1)) * 100)}%` }}
          />
        </div>
      )}
    </div>
  )
}
