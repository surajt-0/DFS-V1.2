const LABELS = {
  csv_export: 'CSV export',
  xlsx_export: 'XLSX export',
  json_export: 'JSON export',
  pdf_reports: 'PDF reports',
  audit_log: 'Audit log access',
  local_scan: 'Local scan',
  data_recovery: 'Deleted-data recovery',
  dns_details: 'DNS details',
}

export default function FileAccessBadges({ fileAccess }) {
  if (!fileAccess) return null
  return (
    <div className="file-access">
      <div className="file-access-title">File access</div>
      <ul className="file-access-list">
        {Object.entries(LABELS).map(([key, label]) => {
          const on = !!fileAccess[key]
          return (
            <li key={key} className={on ? 'on' : 'off'}>
              <span className="dot" />
              {label}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
