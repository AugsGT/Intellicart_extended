import { useEffect, useState } from 'react'
import { getInterventions } from '../api'
import type { Intervention } from '../types'
import StatCard from '../StatCard'
import { formatDateTime, formatPrice } from '../../utils/format'

function InterventionsPage() {
  const [interventions, setInterventions] = useState<Intervention[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getInterventions()
      .then((page) => setInterventions(page.results))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  // "Sent" means shown to a customer; NO_ACTION decisions are only logged.
  const sent = interventions.filter((i) => i.status !== 'LOGGED')
  const recovered = sent.filter((i) => i.outcome === 'RECOVERED')
  const clicked = sent.filter((i) => i.clicked_at)
  const rate = (part: number) => (sent.length > 0 ? `${((part / sent.length) * 100).toFixed(1)}%` : '-')

  return (
    <div>
      <div className="page-header">
        <h1>Interventions</h1>
      </div>
      <p className="muted" style={{ marginTop: '-0.5rem' }}>
        Every decision the cart-recovery engine made, with the rule and signals behind it. Messages never promise
        discounts or reservations, because Intellicart has neither.
      </p>

      {loading && <p>Loading interventions...</p>}
      {error && <p className="error-message">Could not load interventions: {error}</p>}

      {!loading && !error && (
        <>
          <div className="stats-grid">
            <StatCard label="Messages shown" value={sent.length} />
            <StatCard label="Clicked" value={`${clicked.length} (${rate(clicked.length)})`} />
            <StatCard label="Recovered" value={`${recovered.length} (${rate(recovered.length)})`} />
          </div>

          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Rule</th>
                  <th>Cart value</th>
                  <th>Message</th>
                  <th>Status</th>
                  <th>Outcome</th>
                  <th>Triggered</th>
                </tr>
              </thead>
              <tbody>
                {interventions.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <span className="badge">{i.action}</span>
                    </td>
                    <td className="muted">{i.rule}</td>
                    <td>{formatPrice(i.cart_value)}</td>
                    <td className="muted small">
                      {i.message || '-'} {i.message && <em>({i.message_source})</em>}
                    </td>
                    <td className="muted">{i.status}{i.clicked_at ? ' · clicked' : ''}</td>
                    <td>
                      {i.outcome ? <span className="badge badge-resolved">{i.outcome}</span> : <span className="muted">pending</span>}
                    </td>
                    <td>{formatDateTime(i.created_at)}</td>
                  </tr>
                ))}
                {interventions.length === 0 && (
                  <tr>
                    <td colSpan={7} className="muted">
                      No interventions yet. They appear once a cart sits idle and the scanner flags it.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default InterventionsPage
