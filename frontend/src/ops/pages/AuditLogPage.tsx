import { useEffect, useState } from 'react'
import { getAuditActions, getAuditLog } from '../api'
import type { AuditAction, AuditEntry } from '../types'
import { formatDateTime } from '../../utils/format'

const PAGE_SIZE = 25

function AuditLogPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [total, setTotal] = useState(0)
  const [actions, setActions] = useState<AuditAction[]>([])
  const [action, setAction] = useState('')
  const [actor, setActor] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAuditActions()
      .then(setActions)
      .catch(() => {})
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getAuditLog({ action, actor, since, until, page, page_size: PAGE_SIZE })
      .then((result) => {
        if (cancelled) return
        setEntries(result.results)
        setTotal(result.count)
        setError(null)
      })
      .catch((err: Error) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [action, actor, since, until, page])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const filter = (apply: () => void) => {
    apply()
    setPage(1)
  }

  return (
    <div>
      <div className="page-header">
        <h1>Audit Log</h1>
        <span className="muted">{total} entries</span>
      </div>
      <p className="muted small">
        Who did what, and when. Entries can be added but never edited or deleted. Visible to administrators only.
      </p>

      <div className="audit-filters">
        <select value={action} onChange={(e) => filter(() => setAction(e.target.value))} aria-label="Action">
          <option value="">All actions</option>
          {actions.map((a) => (
            <option key={a.action} value={a.action}>
              {a.description}
            </option>
          ))}
        </select>
        <input placeholder="Person (email)" value={actor} onChange={(e) => filter(() => setActor(e.target.value))} aria-label="Person" />
        <label>
          From <input type="date" value={since} onChange={(e) => filter(() => setSince(e.target.value))} />
        </label>
        <label>
          To <input type="date" value={until} onChange={(e) => filter(() => setUntil(e.target.value))} />
        </label>
      </div>

      {error && <p className="error-message">Could not load the audit log: {error}</p>}
      {loading && <p>Loading...</p>}

      {!loading && !error && (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>What</th>
                <th>From</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className="clickable-row" onClick={() => setOpen(open === entry.id ? null : entry.id)}>
                  <td>{formatDateTime(entry.created_at)}</td>
                  <td>
                    {entry.actor_label || <span className="muted">not logged in</span>}
                    {entry.actor_role && <span className="muted small"> ({entry.actor_role.toLowerCase()})</span>}
                  </td>
                  <td>
                    <span className="badge">{entry.action.replace(/_/g, ' ')}</span>
                  </td>
                  <td>
                    {entry.summary}
                    {open === entry.id && <pre className="audit-details">{JSON.stringify(entry.details, null, 2)}</pre>}
                  </td>
                  <td className="muted small">{entry.ip_address ?? '-'}</td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    No entries match.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {pageCount > 1 && (
            <div className="audit-pager">
              <button type="button" className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                ← Newer
              </button>
              <span className="muted">
                Page {page} of {pageCount}
              </span>
              <button type="button" className="btn" disabled={page >= pageCount} onClick={() => setPage(page + 1)}>
                Older →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default AuditLogPage
