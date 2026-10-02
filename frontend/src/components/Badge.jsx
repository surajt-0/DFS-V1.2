export default function Badge({ kind }) {
  if (!kind) return null
  return <span className={`badge badge-${kind}`}>{kind}</span>
}
