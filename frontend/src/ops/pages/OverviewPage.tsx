import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAlerts, getInventory, getOverview } from '../api'
import type { Alert, InventoryItem, Overview } from '../types'
import StatCard from '../StatCard'
import { formatPrice, formatDateTime } from '../../utils/format'

function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [lowStock, setLowStock] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getOverview(), getAlerts(false), getInventory()])
      .then(([overviewData, alertPage, inventoryPage]) => {
        setOverview(overviewData)
        setAlerts(alertPage.results.slice(0, 5))
        setLowStock(inventoryPage.results.filter((i) => i.status !== 'healthy').slice(0, 5))
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p>Loading overview...</p>
  if (error) return <p className="error-message">Could not load overview: {error}</p>
  if (!overview) return null

  return (
    <div>
      <div className="page-header">
        <h1>Operations Overview</h1>
      </div>

      <div className="stats-grid">
        <StatCard label="Orders" value={overview.total_orders} />
        <StatCard label="Revenue" value={formatPrice(overview.total_revenue)} />
        <StatCard
          label="Open Alerts"
          value={overview.open_alerts}
          accent={overview.open_alerts > 0 ? 'danger' : 'default'}
        />
        <StatCard label="Stock Units" value={overview.total_stock_units} />
      </div>

      <div className="overview-columns">
        <div className="panel">
          <div className="page-header">
            <h2>Recent Alerts</h2>
            <Link to="/ops/alerts">View all →</Link>
          </div>
          {alerts.length === 0 ? (
            <p className="muted">No open alerts.</p>
          ) : (
            <ul className="simple-list">
              {alerts.map((alert) => (
                <li key={alert.id}>
                  <span className={`badge badge-${alert.severity}`}>{alert.severity}</span>
                  <span>{alert.message}</span>
                  <span className="muted small">{formatDateTime(alert.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel">
          <div className="page-header">
            <h2>Stock Needing Attention</h2>
            <Link to="/ops/inventory">View all →</Link>
          </div>
          {lowStock.length === 0 ? (
            <p className="muted">All products are healthy.</p>
          ) : (
            <ul className="simple-list">
              {lowStock.map((item) => (
                <li key={item.product_id}>
                  <span className={`badge badge-${item.status}`}>{item.status.replace('_', ' ')}</span>
                  <span>{item.name}</span>
                  <span className="muted small">{item.stock} left</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

export default OverviewPage
