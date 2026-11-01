import { useEffect, useState } from 'react'
import { getHighIntentCustomers, getRecommendationStats } from '../api'
import type { HighIntentCustomer, RecommendationStat } from '../types'
import { formatDateTime } from '../../utils/format'

const percent = (value: number | null) => (value === null ? '-' : `${(value * 100).toFixed(1)}%`)

function CustomerIntelligencePage() {
  const [customers, setCustomers] = useState<HighIntentCustomer[]>([])
  const [stats, setStats] = useState<RecommendationStat[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getHighIntentCustomers(), getRecommendationStats()])
      .then(([people, recommendationStats]) => {
        setCustomers(people)
        setStats(recommendationStats)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1>Customer Intelligence</h1>
      </div>

      {loading && <p>Loading...</p>}
      {error && <p className="error-message">Could not load customer intelligence: {error}</p>}

      {!loading && !error && (
        <>
          <h2>High-intent customers</h2>
          <p className="muted" style={{ marginTop: '-0.5rem' }}>
            Customers scored HIGH or MEDIUM on their recent activity. Each score shows exactly which signals produced it.
          </p>
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Tier</th>
                  <th>Score</th>
                  <th>Views</th>
                  <th>Searches</th>
                  <th>Cart adds</th>
                  <th>Cart removals</th>
                  <th>Checkout started</th>
                  <th>Prior orders</th>
                  <th>Scored</th>
                </tr>
              </thead>
              <tbody>
                {customers.map((c, index) => (
                  <tr key={`${c.user_id ?? c.session_id}-${index}`}>
                    <td className="muted">{c.user_id ? `User #${c.user_id}` : `Guest ${c.session_id.slice(0, 8)}`}</td>
                    <td>
                      <span className={`badge ${c.tier === 'HIGH' ? 'badge-high' : 'badge-medium'}`}>{c.tier}</span>
                    </td>
                    <td>{c.score}</td>
                    <td>{c.basis.view_count}</td>
                    <td>{c.basis.search_count}</td>
                    <td>{c.basis.cart_add_count}</td>
                    <td>{c.basis.cart_remove_count}</td>
                    <td>{c.basis.checkout_started ? 'Yes' : 'No'}</td>
                    <td>{c.basis.prior_orders}</td>
                    <td>{formatDateTime(c.computed_at)}</td>
                  </tr>
                ))}
                {customers.length === 0 && (
                  <tr>
                    <td colSpan={10} className="muted">
                      No high or medium-intent customers scored yet. Scores are computed when a cart is flagged as abandoned.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <h2 style={{ marginTop: '2rem' }}>Recommendation performance</h2>
          <p className="muted" style={{ marginTop: '-0.5rem' }}>
            &quot;Served&quot; counts recommendation lists shown to shoppers. Purchases are attributed when a customer buys a
            product they clicked within 7 days, which shows association rather than proof of cause.
          </p>
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Kind</th>
                  <th>Lists served</th>
                  <th>Clicks</th>
                  <th>Click rate</th>
                  <th>Purchases</th>
                  <th>Purchase rate (of clicks)</th>
                </tr>
              </thead>
              <tbody>
                {stats.map((row) => (
                  <tr key={row.kind}>
                    <td>{row.kind.replace(/_/g, ' ')}</td>
                    <td>{row.served}</td>
                    <td>{row.clicks}</td>
                    <td>{percent(row.click_rate)}</td>
                    <td>{row.purchases}</td>
                    <td>{percent(row.purchase_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default CustomerIntelligencePage
