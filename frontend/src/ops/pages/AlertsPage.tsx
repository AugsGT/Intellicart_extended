import { useEffect, useState } from 'react'
import { getAlerts, resolveAlert } from '../api'
import type { Alert } from '../types'
import { formatDateTime } from '../../utils/format'

function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [showResolved, setShowResolved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [resolving, setResolving] = useState<number | null>(null)

  const load = () => {
    setLoading(true)
    getAlerts(showResolved ? undefined : false)
      .then((page) => setAlerts(page.results))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [showResolved])

  const handleResolve = async (alertId: number) => {
    setResolving(alertId)
    try {
      await resolveAlert(alertId)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not resolve alert')
    } finally {
      setResolving(null)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Alerts</h1>
        <label className="checkbox-label">
          <input type="checkbox" checked={showResolved} onChange={(e) => setShowResolved(e.target.checked)} />
          Show resolved
        </label>
      </div>

      {loading && <p>Loading alerts...</p>}
      {error && <p className="error-message">{error}</p>}

      {!loading && (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Severity</th>
                <th>Message</th>
                <th>Type</th>
                <th>Raised</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.id}>
                  <td>
                    <span className={`badge badge-${alert.severity}`}>{alert.severity}</span>
                  </td>
                  <td>{alert.message}</td>
                  <td className="muted">{alert.type}</td>
                  <td>{formatDateTime(alert.created_at)}</td>
                  <td>
                    {alert.resolved ? (
                      <span className="badge badge-resolved">resolved</span>
                    ) : (
                      <button
                        type="button"
                        className="btn"
                        disabled={resolving === alert.id}
                        onClick={() => handleResolve(alert.id)}
                      >
                        {resolving === alert.id ? 'Resolving...' : 'Resolve'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {alerts.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    No alerts to show.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default AlertsPage
